import asyncio
import logging
from asyncio.queues import QueueEmpty
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from fastapi import HTTPException

from pseudo_trigger.aiohttp_session import aio_session
from pseudo_trigger.expressions import eval_expressions
from pseudo_trigger.log import setup_python_logging
from pseudo_trigger.models import (
    ActionStatus,
    ActionStatusValue,
    Event,
    InternalTrigger,
    ResponseTrigger,
    TriggerState,
)
from pseudo_trigger.persistence import remove_trigger, update_trigger

log = logging.getLogger(__name__)
setup_python_logging(log)

QUEUES_RECEIVE_SCOPE = (
    "https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/receive"
)

_LOCAL_FAILURE_ACTION_ID = "trigger_action_failure"

_MAX_POLL_TIME = 30.0
_MIN_POLL_TIME = 1.0


# The state of the reaper task which can be considered a proxy for the state of all
# asynch tasks. The first item in the list is the state of async polling and the second
# element is the Task for the reaper. When the first element goes to False, all tasks,
# including the reaper, should exit.
reaper_state: List[Union[bool, asyncio.Task]] = [False, None]


@dataclass
class TriggerStateRecord:
    __slots__ = ["state"]
    state: TriggerState


_internal_trigger_states: Dict[str, TriggerStateRecord] = defaultdict(
    lambda: TriggerStateRecord(TriggerState.PENDING)
)


def _get_trigger_state_record(
    trigger_id: str, initial_value: TriggerState = TriggerState.PENDING
) -> TriggerStateRecord:
    trigger_state_rec = _internal_trigger_states[trigger_id]
    return trigger_state_rec


def get_trigger_state(trigger_id: str) -> TriggerState:
    return _get_trigger_state_record(trigger_id).state


def set_trigger_state(trigger_id: str, state: TriggerState) -> TriggerState:
    trigger_state_rec = _get_trigger_state_record(trigger_id, initial_value=state)
    r = trigger_state_rec.state
    if r is TriggerState.DELETING:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change state of Trigger {trigger_id} in state DELETEING",
        )
    trigger_state_rec.state = state
    return r


def _error_action_status(
    msg: str, action_id: str = _LOCAL_FAILURE_ACTION_ID
) -> ActionStatus:
    return ActionStatus(
        action_id=action_id,
        details=msg,
        creator_id="Unknown For Now",
        status=ActionStatusValue.FAILED,
    )


async def auth_header_for_scope(
    scope: str, trigger: InterruptedError
) -> Dict[str, Any]:
    action_token = trigger.token_set.dependent_tokens.get(scope)
    req_headers = {"Authorization": f"Bearer {action_token.access_token}"}
    return req_headers


async def check_action_result(
    action_resp,
    trigger: InternalTrigger,
    action_id: Optional[str] = _LOCAL_FAILURE_ACTION_ID,
) -> ActionStatus:
    log.info("Action Result for trigger_id={trigger.trigger_id}: {action_resp}")
    if 200 <= action_resp.status < 300:
        action_status_dict = await action_resp.json()
        if action_status_dict.get("status") in {"SUCCEEDED", "FAILED"}:
            action_id = action_status_dict.get("action_id")
            auth_header = await auth_header_for_scope(trigger.action_scope, trigger)
            release_resp = await aio_session.post(
                f"{trigger.action_url}/{action_id}/release", headers=auth_header
            )
            if 200 <= release_resp.status < 300:
                action_status_dict = await release_resp.json()
    else:
        action_status_dict = {
            "action_id": action_id,
            "status": ActionStatusValue.FAILED,
            "details": await action_resp.text(),
        }
    action_status = ActionStatus(**action_status_dict)
    trigger.last_action_status = action_status
    return action_status


async def process_event(
    trigger: InternalTrigger, event: Event
) -> Optional[ActionStatus]:
    trigger.event_count += 1

    log.info(f"Processing message trigger_id={trigger.trigger_id}, event={event}")
    try:
        names = event.dict()
        names["event_count"] = trigger.event_count
        filter_val_dict = eval_expressions({"filter.=": trigger.event_filter}, names)
        filter_val = filter_val_dict.get("filter")
    except ValueError as ve:
        msg = (
            f"On trigger_id={trigger.trigger_id}: Unable to evaluate expression "
            f"{trigger.event_filter} on values {names} due to {str(ve)}"
        )
        log.info(msg)
        return _error_action_status(msg)

    log.debug(
        f"Filter eval trigger_id={trigger.trigger_id} "
        f"(trigger.event_filter, filter_val, names):= "
        f"{(trigger.event_filter, filter_val, names)}"
    )
    ret_status = None
    if filter_val is True:
        try:
            action_body = eval_expressions(trigger.event_template, names)
        except ValueError as ve:
            msg = (
                f"On trigger_id={trigger.trigger_id}: Unable to evaluate expression "
                f"{trigger.event_template} on values {names} due to {str(ve)}"
            )
            log.info(msg)
            return _error_action_status(msg)

        log.debug(
            f"Body eval trigger_id={trigger.trigger_id} (action_body):= {(action_body)}"
        )
        req_body = {"request_id": event.event_id, "body": action_body}

        auth_header = await auth_header_for_scope(trigger.action_scope, trigger)
        run_resp = await aio_session.post(
            f"{trigger.action_url}/run", json=req_body, headers=auth_header
        )
        ret_status = await check_action_result(run_resp, trigger)
    return ret_status


async def poll_action_id(trigger: InternalTrigger, action_id: str) -> ActionStatus:
    auth_header = await auth_header_for_scope(trigger.action_scope, trigger)
    status_resp = await aio_session.get(
        f"{trigger.action_url}/{action_id}/status", headers=auth_header
    )
    return await check_action_result(status_resp, trigger, action_id=action_id)


async def poller(trigger: InternalTrigger) -> ResponseTrigger:
    try:
        poll_time = 5.0
        # action_tasks: Set[asyncio.Task] = set()
        # queue_poll_tasks: Set[asyncio.Task] = set()
        outstanding_action_ids: Set[str] = set()
        trigger_id = trigger.trigger_id
        trigger_state_rec = _get_trigger_state_record(trigger_id)
        # We keep going as long as the trigger is enabled, or if we have actions to
        # monitor and the trigger hasn't been entirely deleted
        while (
            reaper_state[0] is True
            and trigger_state_rec.state is TriggerState.ENABLED
            or (
                trigger_state_rec.state is not TriggerState.DELETING
                and len(outstanding_action_ids) > 0
            )
        ):
            queue_id = trigger.queue_id
            queue_msgs_url = (
                f"https://queues.api.globus.org/v1/queues/{queue_id}/messages"
            )
            if poll_time > _MAX_POLL_TIME:
                poll_time = _MAX_POLL_TIME
            if poll_time < _MIN_POLL_TIME:
                poll_time = _MIN_POLL_TIME
            log.debug(f"Polling Wait trigger_id={trigger_id}, poll_time={poll_time}")
            await asyncio.sleep(poll_time)
            log.debug(f"Starting Poll trigger_id={trigger_id}")

            event_processing_tasks: Set[asyncio.Task] = set()
            action_status_tasks: Set[asyncio.Task] = set()

            if trigger_state_rec.state is TriggerState.ENABLED:
                # Do this each time to allow for refresh
                queues_auth_header = await auth_header_for_scope(
                    QUEUES_RECEIVE_SCOPE, trigger
                )
                msgs_response = await aio_session.get(
                    queue_msgs_url + "?max_messages=10",
                    headers=queues_auth_header,
                )
                if 200 <= msgs_response.status < 300:
                    msgs_json = await msgs_response.json()
                    msg_list = msgs_json.get("data", [])
                    log.debug(
                        f"Poller trigger_id={trigger_id}, queue_id={queue_id} received {len(msg_list)} messages"
                    )
                    for msg in msg_list:
                        event = Event.from_queue_msg(msg)
                        trigger.last_event = event
                        process_event_task = asyncio.create_task(
                            process_event(trigger, event)
                        )
                        event_processing_tasks.add(process_event_task)
                        msg_delete = await aio_session.delete(
                            queue_msgs_url,
                            json={
                                "data": [{"receipt_handle": msg.get("receipt_handle")}]
                            },
                            headers=queues_auth_header,
                        )
                        msg_delete_text = await msg_delete.text()
                        log.debug(
                            f"message delete (msg_delete_json):= {(msg_delete_text)}"
                        )

                        if 200 <= msg_delete.status < 300:
                            pass
                else:
                    text = await msgs_response.text()
                    log.debug(
                        f"trigger_id={trigger_id} Got unexpected response from queue {queue_id}: "
                        f"{msgs_response} containing {text}"
                    )
                    trigger.last_action_status = _error_action_status(
                        f"Error reading from queue: {text}"
                    )
                    update_trigger(trigger)

            for action_id in outstanding_action_ids:
                action_status_task = asyncio.create_task(
                    poll_action_id(trigger, action_id)
                )
                action_status_tasks.add(action_status_task)

            if action_status_tasks or event_processing_tasks:
                all_tasks = list(action_status_tasks.union(event_processing_tasks))
                action_statuses: Iterable[
                    Optional[ActionStatus]
                ] = await asyncio.gather(*all_tasks)
                # Reset to just include the active responses
                outstanding_action_ids = set()
                for action_status in action_statuses:
                    if action_status is not None and not action_status.is_complete:
                        outstanding_action_ids.add(action_status.action_id)
                update_trigger(trigger)
                poll_time = poll_time / 2.0
            else:
                poll_time = poll_time * 2.0

    except Exception as e:
        log.error(f"Error on poller for {trigger.trigger_id}: {str(e)}", exc_info=True)
        trigger_state_rec.state = TriggerState.PENDING
    finally:
        log.info(f"Poller for {trigger.trigger_id} exiting")
    # Set final state to match the internal tracking state
    trigger.state = trigger_state_rec.state
    update_trigger(trigger)
    return trigger


_task_queue = asyncio.Queue(maxsize=100)


async def reaper(task_queue: asyncio.Queue):
    log.info("REAPER STARTING...")
    try:
        poll_tasks = set()

        while reaper_state[0] is True or len(poll_tasks) > 0:
            try:
                poll_task = task_queue.get_nowait()
                poll_tasks.add(poll_task)
            except QueueEmpty:
                pass

            if len(poll_tasks) == 0:
                await asyncio.sleep(10)
                continue

            done, pending = await asyncio.wait(poll_tasks, timeout=10)

            for d in done:
                d_task: InternalTrigger = await d
                log.info(f"Completed task {d}, return: {d_task}")
                poll_tasks.remove(d)
                if d_task.state is TriggerState.DELETING:
                    remove_trigger(d_task.trigger_id)
    except Exception as e:
        log.error(f"Reaper failed on {(str(e))}")
    log.info("REAPER EXITING...")


async def start_poller(trigger: InternalTrigger) -> asyncio.Task:
    log.info(f"Starting polling for trigger {trigger.trigger_id}")
    poll_task = asyncio.create_task(
        poller(trigger), name=f"Poller for {trigger.trigger_id}"
    )
    await _task_queue.put(poll_task)
    return poll_task


async def init_polling():
    reaper_state[0] = True
    reaper_state[1] = asyncio.create_task(reaper(_task_queue), name="Reaper")


async def shutdown_polling():
    reaper_state[0] = False
    reaper_result = await asyncio.wait_for(reaper_state[1])

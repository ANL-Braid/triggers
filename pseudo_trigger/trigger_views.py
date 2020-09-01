import asyncio
import json
import logging
import sys
import uuid
from asyncio.queues import QueueEmpty
from enum import Enum, unique
from json import JSONDecodeError
from typing import Any, Dict, List, Mapping, Optional, Set, Union

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl

from pseudo_trigger.aiohttp_session import aio_session
from pseudo_trigger.auth_utils import AuthInfo, get_scope_for_dependent_set
from pseudo_trigger.expressions import eval_expressions

log = logging.getLogger(__name__)

# create console handler and set level to debug
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
log.addHandler(ch)

MANAGE_TRIGGERS_SCOPE = "https://auth.globus.org/scopes/5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"

QUEUES_RECEIVE_SCOPE = (
    "https://auth.globus.org/scopes/3170bf0b-6789-4285-9aba-8b7875be7cbc/receive"
)

app = FastAPI()


class Trigger(BaseModel):
    queue_id: uuid.UUID
    action_url: HttpUrl
    action_scope: Optional[HttpUrl]
    event_filter: str
    event_template: Dict[str, str]


class Event(BaseModel):
    body: Dict[str, Any]
    event_id: str
    sent_by_effective_identity: str
    timestamp: str
    sent_by_app: Optional[str] = None
    sent_by_identity_set: Optional[List[str]] = None

    @staticmethod
    def from_queue_msg(queue_msg: Dict[str, Any]) -> "Event":
        message_body = queue_msg.get("message_body", "")
        try:
            event_body = json.loads(message_body)
        except JSONDecodeError:
            event_body = {"message": message_body}
        event_id = queue_msg.get("message_id", "")
        e = Event(
            body=event_body,
            event_id=event_id,
            sent_by_effective_identity=queue_msg.get("sent_by_effective_identity"),
            timestamp=queue_msg.get("sent_timestamp"),
            sent_by_app=queue_msg.get("sent_by_app"),
            sent_by_identity_set=queue_msg.get("sent_by_identity_set"),
        )
        return e


@unique
class TriggerState(Enum):
    PENDING = "PENDING"
    ENABLED = "ENABLED"
    NO_QUEUE = "NO_QUEUE"
    DELETING = "DELETING"


class ResponseTrigger(Trigger):
    id: str
    created_by: str
    globus_auth_scope: HttpUrl
    state: TriggerState
    last_action_status: Dict[str, Any]
    event_count: int = 0
    last_event: Optional[Event] = None


class InternalTrigger(ResponseTrigger):
    access_token: str = None
    refresh_token: str = None
    expiration_time: int = 0
    all_action_status: List[Dict[str, Any]]


_triggers: Dict[str, InternalTrigger] = {}


async def process_event(
    trigger: InternalTrigger, auth_info: AuthInfo, event: Event
) -> Dict[str, Any]:
    print(f"DEBUG process_event (event):= {(event)}")
    names = event.dict()
    filter_val_dict = eval_expressions({"filter.=": trigger.event_filter}, names)
    filter_val = filter_val_dict.get("filter")
    print(
        f"DEBUG filter eval (trigger.event_filter, filter_val, names):= {(trigger.event_filter, filter_val, names)}"
    )
    trigger.event_count += 1
    if filter_val:
        print("Filter TRUE")
        action_body = eval_expressions(trigger.event_template, names)
        print(f"DEBUG body eval (action_body):= {(action_body)}")
        req_body = {"request_id": event.event_id, "body": action_body}
        dep_tokens = await auth_info.dependent_tokens_by_scope
        print(
            f"DEBUG action tokens (trigger.action_scope,dep_tokens):= {(trigger.action_scope,dep_tokens)}"
        )

        action_token = dep_tokens.get(trigger.action_scope)
        req_headers = {"Authorization": f"Bearer {action_token.access_token}"}
        run_resp = await aio_session.post(
            f"{trigger.action_url}/run", json=req_body, headers=req_headers
        )
        if 200 <= run_resp.status < 300:
            resp = await run_resp.json()
            return resp
        else:
            return {"Action Failure": await run_resp.text()}


async def poller(trigger: InternalTrigger, auth_info: AuthInfo) -> ResponseTrigger:
    try:
        queue_id = trigger.queue_id
        poll_time = 5.0
        queue_msgs_url = f"https://queues.api.globus.org/v1/queues/{queue_id}/messages"
        action_tasks: Set[asyncio.Task] = set()
        queue_poll_tasks: Set[asyncio.Task] = set()
        while trigger.state is TriggerState.ENABLED:
            if poll_time > 30.0:
                poll_time = 30.0
            if poll_time < 1.0:
                poll_time = 1.0
            print("POLLING WAIT...")
            if action_tasks:
                done, pending = await asyncio.wait(action_tasks, timeout=poll_time)
            else:
                done = set()
                pending = set()
                await asyncio.sleep(poll_time)
            print("POLLING WAIT END...")
            # Do this each time to allow for refresh
            dep_tokens = await auth_info.dependent_tokens_by_scope
            queue_token = dep_tokens.get(QUEUES_RECEIVE_SCOPE)

            queues_auth_header = {
                "Authorization": f"Bearer {queue_token.access_token}",
                "Content-Type": "application/json",
            }
            msgs_response = await aio_session.get(
                queue_msgs_url + "?max_messages=10",
                headers=queues_auth_header,
            )
            if 200 <= msgs_response.status < 300:
                msgs_json = await msgs_response.json()
                msg_list = msgs_json.get("data", [])
                if msg_list:
                    poll_time = poll_time / 2.0
                else:
                    poll_time = poll_time * 2.0
                print(f"DEBUG poller (msgs_json):= {(msgs_json)}")
                for msg in msg_list:
                    event = Event.from_queue_msg(msg)
                    action_status = await process_event(trigger, auth_info, event)
                    print(f"DEBUG Action Status (action_status):= {(action_status)}")
                    trigger.last_action_status = action_status
                    trigger.all_action_status.append(action_status)
                    msg_delete = await aio_session.delete(
                        queue_msgs_url,
                        json={"data": [{"receipt_handle": msg.get("receipt_handle")}]},
                        headers=queues_auth_header,
                    )
                    msg_delete_text = await msg_delete.text()
                    print(
                        f"DEBUG message delete (msg_delete_json):= {(msg_delete_text)}"
                    )

                    if 200 <= msg_delete.status < 300:
                        pass
            else:
                text = await msgs_response.text()
                print(
                    f"Got unexpected response from queue {queue_id}: "
                    f"{msgs_response} containing {text}"
                )
                break
    except Exception as e:
        print(f"Error on poller for {trigger.id}: str(e)")
        log.error(f"Error on poller for {trigger.id}", exc_info=e)
    finally:
        print(f"Poller for {trigger.id} exiting")
        log.info(f"Poller for {trigger.id} exiting")
    return trigger


async def reaper(task_queue: asyncio.Queue):
    print("REAPER STARTING...")

    try:
        poll_tasks = set()

        while True:
            try:
                poll_task = task_queue.get_nowait()
                print(f"DEBUG reaper (poll_task):= {(poll_task)}")

                poll_tasks.add(poll_task)
            except QueueEmpty:
                pass

            if len(poll_tasks) == 0:
                await asyncio.sleep(10)
                continue

            done, pending = await asyncio.wait(poll_tasks, timeout=10)
            print(f"DEBUG reaper (done,pending):= {(done,pending)}")

            for d in done:
                d_task: InternalTrigger = await d
                print(f"Completed task {d}, return: {d_task}")
                log.info(f"Completed task {d}, return: {d_task}")
                poll_tasks.remove(d)
                if d_task.state is TriggerState.DELETING:
                    _triggers.pop(d_task.id, None)
    except Exception as e:
        print(f"DEBUG reaper failed on  (str(e)):= {(str(e))}")


_task_queue = asyncio.Queue(maxsize=100)
reaper_task = asyncio.create_task(reaper(_task_queue), name="Reaper")


async def globus_auth_dependency(
    authorization: Optional[str] = Header(None),
) -> AuthInfo:
    token = ""
    if authorization is not None:
        authorization = authorization.strip()
        if authorization.startswith("Bearer "):
            token = authorization.lstrip("Bearer ")
    auth_info = AuthInfo(token)
    return auth_info


@app.post("/triggers", response_model=ResponseTrigger)
async def create_trigger(
    trigger: Trigger, auth_info: AuthInfo = Depends(globus_auth_dependency)
):
    await auth_info.authorize(MANAGE_TRIGGERS_SCOPE, {"all_authenticated_users"})
    if trigger.action_scope is None:
        try:
            action_introspect = await aio_session.get(str(trigger.action_url))
            if 200 <= action_introspect.status < 300:
                scope = (await action_introspect.json()).get("globus_auth_scope")
                trigger.action_scope = scope
        except Exception as e:
            print(
                f"Failed to retrieve scope from url {trigger.action_url} due to {str(e)}"
            )

    if trigger.action_scope is None:
        raise HTTPException(
            status_code=400,
            detail=f"'auth_scope' not provided and unable to retrieve from {str(trigger.action_url)}",
        )
    scope_for_trigger = await get_scope_for_dependent_set(
        [trigger.action_scope, QUEUES_RECEIVE_SCOPE]
    )

    trigger_id = str(uuid.uuid4())
    vals = trigger.dict()
    internal_trigger = InternalTrigger(
        id=trigger_id,
        created_by=auth_info.sub,
        globus_auth_scope=scope_for_trigger,
        state=TriggerState.PENDING,
        last_action_status={},
        all_action_status=[],
        **vals,
    )
    _triggers[trigger_id] = internal_trigger
    return internal_trigger


def _lookup_trigger(trigger_id: str) -> InternalTrigger:
    trigger = _triggers.get(trigger_id)
    if trigger is None:
        raise HTTPException(
            status_code=404, detail=f"No trigger with id '{trigger_id}'"
        )
    return trigger


@app.get("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def get_trigger(trigger_id: str) -> InternalTrigger:
    return _lookup_trigger(trigger_id)


@app.post("/triggers/{trigger_id}/enable", response_model=ResponseTrigger)
async def enable_trigger(
    trigger_id: str,
    auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> InternalTrigger:
    trigger = _lookup_trigger(trigger_id)

    await auth_info.authorize(trigger.globus_auth_scope, {trigger.created_by})

    trigger.state = TriggerState.ENABLED

    poll_task = asyncio.create_task(
        poller(trigger, auth_info), name=f"Poller for {trigger_id}"
    )
    await _task_queue.put(poll_task)
    return trigger


@app.post("/triggers/{trigger_id}/disable", response_model=ResponseTrigger)
async def disable_trigger(trigger_id: str) -> InternalTrigger:
    trigger = _lookup_trigger(trigger_id)
    trigger.state = TriggerState.PENDING
    return trigger


@app.post("/triggers/{trigger_id}/event")
async def send_event(trigger_id: str, body: Union[str, Mapping[str, Any]]) -> None:
    trigger = _lookup_trigger(trigger_id)
    if trigger.state is not TriggerState.ENABLED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send even to trigger in state {str(trigger.state)}",
        )
    return {}


@app.delete("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def delete_trigger(trigger_id: str) -> InternalTrigger:
    trigger = _lookup_trigger(trigger_id)
    trigger.state = TriggerState.DELETING
    return trigger

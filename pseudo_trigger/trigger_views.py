import logging
import uuid
from typing import Any, List, Mapping, Optional, Union

from fastapi import Depends, FastAPI, Header, HTTPException

from pseudo_trigger.aiohttp_session import aio_session
from pseudo_trigger.auth_utils import AuthInfo, get_scope_for_dependent_set
from pseudo_trigger.log import setup_python_logging
from pseudo_trigger.models import (
    InternalTrigger,
    ResponseTrigger,
    Trigger,
    TriggerState,
)
from pseudo_trigger.persistence import (
    lookup_trigger,
    remove_trigger,
    scan_triggers,
    store_trigger,
    update_trigger,
)
from pseudo_trigger.tasks import QUEUES_RECEIVE_SCOPE, set_trigger_state, start_poller

log = logging.getLogger(__name__)
setup_python_logging(log, http=True)


MANAGE_TRIGGERS_SCOPE = "https://auth.globus.org/scopes/5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"


app = FastAPI()


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


@app.get("/status")
@app.get("/")
async def healthcheck():
    return {"status": "ok"}


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
        trigger_id=trigger_id,
        created_by=auth_info.sub,
        globus_auth_scope=scope_for_trigger,
        state=TriggerState.PENDING,
        token_set=await auth_info.token_set,
        all_action_status=[],
        **vals,
    )
    internal_trigger = store_trigger(internal_trigger)
    return internal_trigger


async def _lookup_trigger(
    trigger_id: str, auth_info: Optional[AuthInfo] = None
) -> InternalTrigger:
    trigger = lookup_trigger(trigger_id)
    # log.info(f"lookup({trigger_id}): {trigger}")
    if trigger is None:
        raise HTTPException(
            status_code=404, detail=f"No Trigger with id {trigger_id} found"
        )
    if auth_info is not None:
        await auth_info.authorize(trigger.globus_auth_scope, {trigger.created_by})
    return trigger


@app.get("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def get_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> InternalTrigger:
    return await _lookup_trigger(trigger_id)


@app.get("/triggers", response_model=List[ResponseTrigger])
async def list_triggers(
    auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> List[InternalTrigger]:
    # Make sure the token's been introspected
    token_resp = await auth_info.token_resp
    print(f"DEBUG  (token_resp):= {(token_resp)}")
    triggers = scan_triggers(created_by=auth_info.sub)
    return triggers


@app.post("/triggers/{trigger_id}/enable", response_model=ResponseTrigger)
async def enable_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)

    trigger.state = TriggerState.ENABLED
    trigger.token_set = await auth_info.token_set
    update_trigger(trigger)

    set_trigger_state(trigger_id, TriggerState.ENABLED)
    await start_poller(trigger)

    return trigger


@app.post("/triggers/{trigger_id}/disable", response_model=ResponseTrigger)
async def disable_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)
    set_trigger_state(trigger_id, TriggerState.PENDING)
    return trigger


@app.post("/triggers/{trigger_id}/event")
async def send_event(trigger_id: str, body: Union[str, Mapping[str, Any]]) -> None:
    trigger = await _lookup_trigger(trigger_id)
    if trigger.state is not TriggerState.ENABLED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send even to trigger in state {str(trigger.state)}",
        )
    return {}


@app.delete("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def delete_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)
    prev_state = set_trigger_state(trigger_id, TriggerState.DELETING)
    # If this is enabled, then the polling task will clean it up. Else, we do it here
    if prev_state is not TriggerState.ENABLED:
        remove_trigger(trigger_id)
    return trigger

import os
import time
import typing as t
import uuid

import structlog
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from structlog.contextvars import bind_contextvars, get_contextvars

from braid_triggers.aiohttp_session import aio_session
from braid_triggers.auth_utils import AuthInfo
from braid_triggers.models import (
    InternalTrigger,
    ResponseTrigger,
    Trigger,
    TriggerState,
)
from braid_triggers.persistence import (
    lookup_trigger,
    remove_trigger,
    scan_triggers,
    store_trigger,
    update_trigger,
)
from braid_triggers.tasks import QUEUES_RECEIVE_SCOPE, set_trigger_state, start_poller

log = structlog.get_logger(__name__)

MANAGE_TRIGGERS_SCOPE = (
    "https://auth.globus.org/scopes/9b54c03e-30be-43e7-8b5d-133f94930837"
    "/manage_triggers"
)
ENABLE_TRIGGER_WITH_QUEUE_READ_SCOPE = (
    "https://auth.globus.org/scopes/9b54c03e-30be-43e7-8b5d-133f94930837/"
    "trigger_enable_with_queue_read"
)


app = FastAPI()

service_name = os.getenv("COPILOT_SERVICE_NAME", "concurrent-actions-provider")

route_prefix = f"/{service_name}"
native_router = APIRouter(prefix=route_prefix)


async def globus_auth_dependency(
    authorization: str | None = Header(None),
) -> AuthInfo:
    token = ""
    if authorization is not None:
        authorization = authorization.strip()
        if authorization.startswith("Bearer "):
            token = authorization.lstrip("Bearer ")

    auth_info = AuthInfo(token)
    # Make sure the token has been introspected
    _ = await auth_info.token_resp
    return auth_info


async def globus_auth_required_dependency(
    request: Request,
    auth_info: AuthInfo = Depends(globus_auth_dependency),
) -> AuthInfo:
    if auth_info.sub is None:
        log.info(f"Railed to get authorization info on path {request.url}")
        raise HTTPException(
            status_code=400,
            detail=f"Authorization information required to use method {request.url}",
        )
    return auth_info


@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    req_id = str(uuid.uuid4())
    start_time = time.time()
    bind_contextvars(req_id=req_id)
    response = await call_next(request)
    end_time = time.time()
    run_time = end_time - start_time
    log.info(
        f"{request.method} {request.url.path} {request.query_params}",
        path=request.url.path,
        method=request.method,
        params=request.query_params,
        status_code=response.status_code,
        run_time_ms=round(run_time * 1000),
    )
    return response


@app.exception_handler(Exception)
async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception(exc)
    req_id = get_contextvars().get("req_id", "<unknown>")
    return JSONResponse(
        status_code=500,
        content={
            "message": f"Internal Service Error Encountered: {str(exc)}",
            "req_id": req_id,
        },
    )


@native_router.get("/status")
@app.get("/")
async def healthcheck():
    return {"status": "ok"}


@native_router.post("/triggers", response_model=ResponseTrigger)
async def create_trigger(
    trigger: Trigger, auth_info: AuthInfo = Depends(globus_auth_required_dependency)
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
            detail=(
                "'auth_scope' not provided and unable to retrieve from "
                f"{str(trigger.action_url)}"
            ),
        )

    """
    scope_for_trigger = await get_scope_for_dependent_set(
        [trigger.action_scope, QUEUES_RECEIVE_SCOPE]
    )
    """
    # Use the below to generate a dynamic-dependency based scope
    scope_for_trigger = (
        f"{ENABLE_TRIGGER_WITH_QUEUE_READ_SCOPE}[{trigger.action_scope}]"
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
    trigger_id: str, auth_info: AuthInfo | None = None
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


@native_router.get("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def get_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_required_dependency)
) -> InternalTrigger:
    return await _lookup_trigger(trigger_id)


@native_router.get("/triggers", response_model=list[ResponseTrigger])
async def list_triggers(
    auth_info: AuthInfo = Depends(globus_auth_required_dependency),
) -> list[InternalTrigger]:
    triggers = scan_triggers(created_by=auth_info.sub)
    return triggers


@native_router.post("/triggers/{trigger_id}/enable", response_model=ResponseTrigger)
async def enable_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_required_dependency)
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)

    trigger.state = TriggerState.ENABLED
    trigger.token_set = await auth_info.token_set
    update_trigger(trigger)

    set_trigger_state(trigger_id, TriggerState.ENABLED)
    await start_poller(trigger)

    return trigger


@native_router.post("/triggers/{trigger_id}/disable", response_model=ResponseTrigger)
async def disable_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_required_dependency)
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)
    set_trigger_state(trigger_id, TriggerState.PENDING)
    return trigger


@native_router.post("/triggers/{trigger_id}/event")
async def send_event(trigger_id: str, body: str | t.Mapping[str, t.Any]) -> dict:
    trigger = await _lookup_trigger(trigger_id)
    if trigger.state is not TriggerState.ENABLED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send even to trigger in state {str(trigger.state)}",
        )
    return {}


@native_router.delete("/triggers/{trigger_id}", response_model=ResponseTrigger)
async def delete_trigger(
    trigger_id: str, auth_info: AuthInfo = Depends(globus_auth_required_dependency)
) -> InternalTrigger:
    trigger = await _lookup_trigger(trigger_id, auth_info)
    prev_state = set_trigger_state(trigger_id, TriggerState.DELETING)
    # If this is enabled, then the polling task will clean it up. Else, we do it here
    if prev_state is not TriggerState.ENABLED:
        remove_trigger(trigger_id)
    return trigger


app.include_router(native_router)

import uvicorn

from braid_triggers.models import TriggerState
from braid_triggers.persistence import enum_triggers, init_persistence
from braid_triggers.tasks import init_polling, set_trigger_state, start_poller
from braid_triggers.trigger_views import app as trigger_app

from .logs import init_logging
from .settings import get_settings


@trigger_app.on_event("startup")
async def startup():
    print("#####################")
    print("# PSEUDO TRIGGER STARTING UP....")
    print("#####################")

    settings = get_settings()
    init_logging(log_level=settings.log_level, log_format=settings.log_format)

    init_persistence()

    await init_polling()
    enabled_triggers = enum_triggers(state="ENABLED")

    uvicorn_log_config = uvicorn.config.LOGGING_CONFIG

    uvicorn_log_config["formatters"]["access"][
        "fmt"
    ] = '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'

    # "{asctime} {levelname:7} ({name}:{lineno}) {message}"

    for trigger in enabled_triggers:
        set_trigger_state(trigger.trigger_id, TriggerState.ENABLED)
        await start_poller(trigger)


@trigger_app.on_event("shutdown")
async def shutdown():
    print("!!!!!!!!!!!!!!!!!!!!!")
    print("! PSEUDO TRIGGER SHUTTING DOWN....")
    print("!!!!!!!!!!!!!!!!!!!!!")
    await init_polling()


app = trigger_app

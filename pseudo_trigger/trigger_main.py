import uvicorn

from pseudo_trigger.models import TriggerState
from pseudo_trigger.persistence import enum_triggers, init_persistence
from pseudo_trigger.tasks import init_polling, set_trigger_state, start_poller
from pseudo_trigger.trigger_views import app as trigger_app


@trigger_app.on_event("startup")
async def startup():
    print("#####################")
    print("# PSEUDO TRIGGER STARTING UP....")
    print("#####################")
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

from pseudo_trigger.models import TriggerState
from pseudo_trigger.persistence import enum_triggers, init_persistence
from pseudo_trigger.tasks import init_polling, set_trigger_state, start_poller
from pseudo_trigger.trigger_views import app as trigger_app
from pseudo_trigger.log import setup_python_logging

import logging

log = logging.getLogger(__name__)
setup_python_logging(log)


init_persistence()
@trigger_app.on_event("startup")
async def startup(): 
    await init_polling()
    enabled_triggers = enum_triggers(state="ENABLED")

    for trigger in enabled_triggers:
        set_trigger_state(trigger.id, TriggerState.ENABLED)
        await start_poller(trigger)

app = trigger_app

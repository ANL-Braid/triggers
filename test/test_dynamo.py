import os
import uuid

from pseudo_trigger.models import InternalTrigger, Token, TokenSet, TriggerState
from pseudo_trigger.persistence import (
    init_persistence,
    lookup_trigger,
    scan_triggers,
    store_trigger,
)

os.environ["TRIGGER_ENVIRONMENT"] = "pytest"

init_persistence()


def _create_dummy_scope_string(scope_suffix: str = "dummy_scope") -> str:
    return f"https://auth.globus.org/client_id/{scope_suffix}"


def _create_dummy_token(scope_suffix: str = "dummy_scope") -> Token:
    t = Token(
        access_token="_dummy_access",
        scope=_create_dummy_scope_string(scope_suffix),
        refresh_token="_dummy_refresh",
        expiration_time=123456789,
    )
    return t


def test_store_trigger():
    trigger_id = str(uuid.uuid4())
    created_by = str(uuid.uuid4())
    trigger = InternalTrigger(
        queue_id=uuid.uuid4(),
        action_url="https://example.com",
        event_filter="True",
        action_scope=None,
        event_template={"foo": "bar"},
        trigger_id=trigger_id,
        created_by=created_by,
        globus_auth_scope=_create_dummy_scope_string("trigger_scope"),
        state=TriggerState.ENABLED,
        token_set=TokenSet(
            user_token=_create_dummy_token("user_scope"), dependent_tokens={}
        ),
        all_action_status=[],
    )
    trigger2 = InternalTrigger(
        queue_id=uuid.uuid4(),
        action_url="https://example.com",
        event_filter="True",
        action_scope=None,
        event_template={"foo": "bar"},
        trigger_id=str(uuid.uuid4()),
        created_by=created_by,
        globus_auth_scope=_create_dummy_scope_string("trigger_scope"),
        state=TriggerState.ENABLED,
        token_set=TokenSet(
            user_token=_create_dummy_token("user_scope"), dependent_tokens={}
        ),
        all_action_status=[],
    )

    store_trigger(trigger)
    store_trigger(trigger2)

    back_trigger = lookup_trigger(trigger_id)
    assert back_trigger.trigger_id == trigger.trigger_id

    import pdb

    # pdb.set_trace()

    scanned_triggers = scan_triggers(
        created_by=[trigger.created_by, trigger2.created_by]
    )
    assert len(scanned_triggers) == 2
    assert scanned_triggers[0].trigger_id == trigger.trigger_id

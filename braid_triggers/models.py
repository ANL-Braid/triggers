from __future__ import annotations

import datetime
import json
import time
import typing as t
import uuid
from enum import Enum, unique
from json import JSONDecodeError

from pydantic import BaseModel, Field, HttpUrl


class BaseEnum(str, Enum):
    """
    A pythonic Enum class implementation that removes the need to access a
    "value" attribute to get an Enum's representation.
    http://www.cosmicpython.com/blog/2020-10-27-i-hate-enums.html
    """

    def __str__(self) -> str:
        return str.__str__(self)


class ActionStatusValue(BaseEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ActionStatus(BaseModel):
    status: ActionStatusValue
    creator_id: str
    action_id: str
    start_time: datetime.datetime = Field(default_factory=datetime.datetime.now)
    label: str | None = None
    monitor_by: list[str] | None = None
    manage_by: list[str] | None = None
    completion_time: str | None = None
    release_after: str | None = None
    display_status: str | None = None
    details: dict[str, t.Any] | None = None

    def is_complete(self):
        return self.status in (ActionStatusValue.SUCCEEDED, ActionStatusValue.FAILED)


class Event(BaseModel):
    body: dict[str, t.Any]
    event_id: str
    sent_by_effective_identity: str
    timestamp: str
    sent_by_app: str | None = None
    sent_by_identity_set: list[str] | None = None

    @staticmethod
    def from_queue_msg(queue_msg: dict[str, t.Any]) -> "Event":
        message_body = queue_msg.get("message_body", "")
        try:
            event_body = json.loads(message_body)
        except JSONDecodeError as jsde:
            event_body = {"message": message_body, "json_parse_status": str(jsde)}
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


class Token(BaseModel):
    access_token: str
    scope: str
    refresh_token: str
    expiration_time: int
    resource_server: str | None = None
    token_type: str | None = None

    def requires_refresh(self) -> bool:
        now = time.time()
        requires_refresh = now + 300 > self.expiration_time
        return requires_refresh


class TokenSet(BaseModel):
    user_token: Token
    dependent_tokens: t.Mapping[str, Token]


@unique
class TriggerState(BaseEnum):
    PENDING = "PENDING"
    ENABLED = "ENABLED"
    NO_QUEUE = "NO_QUEUE"
    DELETING = "DELETING"
    DELETED = "DELETED"


class Trigger(BaseModel):
    class Config:
        use_enum_values = True

    queue_id: uuid.UUID
    action_url: HttpUrl
    action_scope: HttpUrl | None
    event_filter: str
    event_template: dict[str, t.Any]


class ResponseTrigger(Trigger):
    trigger_id: str
    created_by: str
    globus_auth_scope: HttpUrl
    state: TriggerState
    last_action_status: ActionStatus | None = None
    last_action_statuses: list[ActionStatus] | None = None
    last_error_action_status: ActionStatus | None = None
    event_count: int = 0
    last_event: Event | None = None


class InternalTrigger(ResponseTrigger):
    token_set: TokenSet
    all_action_status: list[ActionStatus]

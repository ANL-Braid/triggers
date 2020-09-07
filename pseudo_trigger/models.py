from __future__ import annotations

import datetime
import json
import time
import uuid
from enum import Enum, auto, unique
from json import JSONDecodeError
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, HttpUrl


class ActionStatusValue(Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ActionStatus(BaseModel):
    status: ActionStatusValue
    creator_id: str
    action_id: str
    start_time: datetime.datetime= Field(default_factory=datetime.datetime.now)
    label: Optional[str] = None
    monitor_by: Optional[List[str]] = None
    manage_by: Optional[List[str]] = None
    completion_time: Optional[str] = None
    release_after: Optional[str] = None
    display_status: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def is_complete(self):
        return self.status in (ActionStatusValue.SUCCEEDED, ActionStatusValue.FAILED)

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


class Token(BaseModel):
    access_token: str
    scope: str
    refresh_token: str
    expiration_time: int
    resource_server: Optional[str] = None
    token_type: Optional[str] = None

    def requires_refresh(self) -> bool:
        now = time.time()
        return True
        # return now + 300 > self.expiration_time
        # return now > self.expires_in + self.creation_time + 1800


class TokenSet(BaseModel):
    user_token: Token
    dependent_tokens: Mapping[str, Token]


@unique
class TriggerState(Enum):
    PENDING = "PENDING"
    ENABLED = "ENABLED"
    NO_QUEUE = "NO_QUEUE"
    DELETING = "DELETING"
    DELETED = "DELETED"


class Trigger(BaseModel):
    queue_id: uuid.UUID
    action_url: HttpUrl
    action_scope: Optional[HttpUrl]
    event_filter: str
    event_template: Dict[str, str]


class ResponseTrigger(Trigger):
    id: str
    created_by: str
    globus_auth_scope: HttpUrl
    state: TriggerState
    last_action_status: Optional[ActionStatus] = None
    event_count: int = 0
    last_event: Optional[Event] = None


class InternalTrigger(ResponseTrigger):
    token_set: TokenSet
    all_action_status: List[ActionStatus]


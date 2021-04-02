import os
from typing import Any, Dict, Optional

from globus_automate_client import ActionClient
from globus_sdk import (
    AccessTokenAuthorizer,
    ClientCredentialsAuthorizer,
    GlobusHTTPResponse,
    RefreshTokenAuthorizer,
)
from globus_sdk.base import BaseClient

from .auth import get_authorizer_for_scope

DEFAULT_BASE_URL = "http://localhost:5001/triggers"
BASE_URL = os.environ.get("PSEUDO_TRIGGER_URL", DEFAULT_BASE_URL)
MANAGE_TRIGGERS_SCOPE = "https://auth.globus.org/scopes/5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"


class TriggerClient(BaseClient):
    allowed_authorizer_types = (
        AccessTokenAuthorizer,
        RefreshTokenAuthorizer,
        ClientCredentialsAuthorizer,
    )

    def __init__(self, client_id: str, *args, **kwargs) -> None:
        self.client_id = client_id
        super().__init__(*args, **kwargs)

    def create(
        self,
        queue_id: str,
        action_url: str,
        event_template: Dict[str, Any],
        event_filter: str = "True",
        action_scope: Optional[str] = None,
    ) -> GlobusHTTPResponse:
        body = {
            "queue_id": queue_id,
            "action_url": action_url,
            "event_filter": event_filter,
            "event_template": event_template,
            "action_scope": action_scope,
        }
        path = self.qjoin_path("triggers")
        return self.post(path, body)

    def lookup(self, trigger_id: str) -> GlobusHTTPResponse:
        path = self.qjoin_path("triggers", trigger_id)
        return self.get(path)

    def list(self) -> GlobusHTTPResponse:
        path = self.qjoin_path("triggers")
        return self.get(path)

    def enable(self, trigger_id: str, scope: Optional[str]) -> GlobusHTTPResponse:
        if scope is None:
            trigger_def = self.lookup(trigger_id)
            scope = trigger_def.data.get("globus_auth_scope")
        authorizer = get_authorizer_for_scope(scope, client_id=self.client_id)
        old_auth = self.authorizer
        self.authorizer = authorizer
        path = self.qjoin_path("triggers", trigger_id, "enable")
        r = self.post(path)
        self.authorizer = old_auth
        return r

    def disable(self, trigger_id: str) -> GlobusHTTPResponse:
        path = self.qjoin_path("triggers", trigger_id, "disable")
        return self.post(path)

    def remove(self, trigger_id: str) -> GlobusHTTPResponse:
        path = self.qjoin_path("triggers", trigger_id)
        return self.delete(path)


def create_trigger_client(client_id: str, base_url: str = BASE_URL) -> TriggerClient:
    authorizer = get_authorizer_for_scope(MANAGE_TRIGGERS_SCOPE, client_id=client_id)

    return TriggerClient(
        client_id,
        "trigger_client",
        base_url=base_url,
        app_name="trigger_client",
        authorizer=authorizer,
    )

import os
from typing import Dict, Optional

from fair_research_login import ConfigParserTokenStorage, NativeClient
from fair_research_login.exc import LocalServerError
from globus_sdk import AccessTokenAuthorizer
from globus_sdk.exc import AuthAPIError

from pseudo_trigger.cli.dynamic_dep_storage import DynamicDependencyTokenStorage

CLIENT_ID = "1602fba0-9893-49cb-a2fe-aa064b452462"
CONFIG_PATH = "~/.globus-triggers.cfg"
CONFIG_FILENAME = os.path.expanduser(CONFIG_PATH)


class MultiScopeTokenStorage(ConfigParserTokenStorage):
    CONFIG_FILENAME = os.path.expanduser(CONFIG_PATH)
    GLOBUS_SCOPE_PREFIX = "https://auth.globus.org/scopes/"
    # Last one is to keep scope names tidy
    # square brackets might be present in a dynamic,
    # dependent scope where the scope dependency is enclosed in square braces
    SECTION_REPLACEMENTS = (("[", "_"), ("]", "_"), ("^" + GLOBUS_SCOPE_PREFIX, ""))

    def __init__(self, scope: Optional[str] = None):
        if scope is not None:
            section = scope
            for replace_pattern, replace_val in self.SECTION_REPLACEMENTS:
                if replace_pattern.startswith("^") and section.startswith(
                    replace_pattern[1:]
                ):
                    section = section.replace(replace_pattern[1:], replace_val, 1)
                else:
                    section = section.replace(replace_pattern, replace_val)
        else:
            section = "default"
        super().__init__(filename=self.CONFIG_FILENAME, section=None)

    def save(self, config):
        import pdb

        pdb.set_trace()
        super().save(config)


def get_authorization_header_for_scope(scope: str, client_id: str = CLIENT_ID) -> Dict:
    authorizer = get_authorizer_for_scope(scope, client_id)
    access_token = authorizer.access_token
    header = {"Authorization": f"Bearer {access_token}"}
    return header


def get_authorizer_for_scope(
    scope: str, client_id: str = CLIENT_ID
) -> AccessTokenAuthorizer:
    client = NativeClient(
        client_id=CLIENT_ID,
        app_name="globus-automate CLI",
        token_storage=DynamicDependencyTokenStorage(CONFIG_FILENAME, [scope]),
    )
    ssh_active = "SSH_CLIENT" in os.environ or "SSH_CONNECTION" in os.environ
    try:
        client.login(
            requested_scopes=[scope],
            refresh_tokens=True,
            no_browser=ssh_active,
            no_local_server=ssh_active,
        )
        authorizers = client.get_authorizers()
        authorizer = next(iter(authorizers.values()))
        return authorizer

    except (LocalServerError, AuthAPIError) as e:
        print(f"Login Unsuccessful: {str(e)}")
        raise SystemExit

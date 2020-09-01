import logging
import time
from base64 import b64encode
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    MutableSequence,
    NamedTuple,
    Optional,
    Set,
)

import cachetools
from fastapi import HTTPException

from pseudo_trigger.aiohttp_session import aio_session
from pseudo_trigger.config import config

AUTH_DOMAIN = "https://auth.globus.org/"

log = logging.getLogger(__name__)


class Token(NamedTuple):
    access_token: str
    scope: str
    resource_server: str
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    creation_time: Optional[int] = time.time()

    def requires_refresh(self) -> bool:
        now = time.time()
        return now > self.expires_in + self.creation_time + 1800


class AuthInfo(object):
    def __init__(self, bearer_token: str):
        self.access_token = bearer_token
        self._token_resp = {}
        self._dependent_tokens = None

    @property
    async def token_resp(self) -> Dict:
        if not self._token_resp:
            if self.access_token:
                token_resp = await introspect_token(self.access_token)
                self._token_resp = token_resp
                for k, v in token_resp.items():
                    setattr(self, k, v)
        return self._token_resp

    @property
    async def user_token(self) -> Token:
        _ = await self.token_resp
        t = Token(
            access_token=self.access_token,
            scope=self.scope,
            resource_server="",
            expires_in=self.exp - time.time(),
            token_type=self.token_type,
        )
        return t

    async def authorize(
        self, required_scope: str, required_principals: Set[str]
    ) -> None:
        if "public" in required_principals:
            return
        token_resp = await self.token_resp
        if token_resp and "all_authenticated_users" in required_principals:
            return
        if required_principals.isdisjoint(set(self.identities_set)):
            raise HTTPException(status_code=401, detail="Unauthorized")

    async def refresh_if_required(self, t: Token) -> Token:
        if t.requires_refresh():
            refresh_reply = await refresh_token(t.refresh_token)
            t = Token(**refresh_reply)
        return t

    @property
    async def dependent_tokens(self) -> List[Token]:
        if self._dependent_tokens is None:
            dep_tokens = await dependent_token_exchange(self.access_token)
            self._dependent_tokens = [Token(**dt) for dt in dep_tokens]
        # Refresh old tokens
        self._dependent_tokens = [
            await self.refresh_if_required(t) for t in self._dependent_tokens
        ]
        return self._dependent_tokens

    @property
    async def dependent_tokens_by_scope(self) -> Dict[str, Token]:
        return {t.scope: t for t in await self.dependent_tokens}


def _client_auth_header(
    client_id: Optional[str] = None, client_secret: Optional[str] = None
) -> Dict[str, str]:
    if client_id is None:
        client_id = config.get("CLIENT_ID")
    if client_secret is None:
        client_secret = config.get("CLIENT_SECRET")
    auth_string = f"{client_id}:{client_secret}"
    return {
        "Authorization": "Basic "
        + b64encode(auth_string.encode("utf-8")).decode("utf-8")
    }


async def _perform_auth_request(
    path: str,
    method: str,
    body: Optional[Mapping] = None,
    path_type: str = "api",
    body_type="json",
):
    if not path.startswith("/"):
        path = "/" + path
    url = f"{AUTH_DOMAIN}v2/{path_type}{path}"
    auth_headers = _client_auth_header()
    body_param = {body_type: body}
    response = await aio_session.request(
        method, url, headers=auth_headers, timeout=30, **body_param
    )
    if not (200 <= response.status < 300):
        resp_text = await response.text()
        log.error(
            f"Failed to {method} resource {url} due return code "
            f"{response.status} with body {resp_text} for "
            f"input body: {body}"
        )
        print(
            f"Failed to {method} resource {url} due return code "
            f"{response.status} with body {resp_text} for "
            f"input body: {body}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to Communicate with Globus Auth: {resp_text}",
        )
    try:
        response_json = await response.json()
    except ValueError:
        log.error(
            f"Failed to parse response from Globus Auth for {method} resource {url} "
            f"with body {response.text} "
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to Communicate with Globus Auth",
        )

    log.info(f"{method} to url {url} returned {response_json}")
    return response_json


async def introspect_token(token: str, client_id: Optional[str] = None) -> Dict:
    params = {"token": token, "include": "identities_set"}
    # Same algorithm as in dependent_token_exchange() to try with flow-specific client id
    # and the Flows service client_id
    for try_client_id in {client_id, None}:
        response_json = await _perform_auth_request(
            "/token/introspect",
            "POST",
            body=params,
            path_type="oauth2",
            body_type="data",
        )
        response_json = response_json
        if response_json.get("active", False):
            return response_json
    msg = f"Expired or invalid Bearer token {response_json}"
    print(msg)
    log.error(msg)
    raise HTTPException(status_code=401, detail=msg)


async def dependent_token_exchange(
    token: str, offline_access: bool = True
) -> List[Dict]:
    params = {
        "grant_type": "urn:globus:auth:grant_type:dependent_token",
        "token": token,
        "access_type": "offline" if offline_access else "online",
    }
    response_json = await _perform_auth_request(
        "/token", "POST", body=params, path_type="oauth2", body_type="data"
    )
    return response_json


async def refresh_token(token: str) -> Dict:
    url = "/token"
    params = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    refresh_resp = await _perform_auth_request(
        url, "GET", body=params, path_type="oauth2", body_type="data"
    )
    return refresh_resp


_my_scope_cache: Optional[Dict[FrozenSet, str]] = None


async def initialize_scope_cache():
    global _my_scope_cache
    if not _my_scope_cache:
        _my_scope_cache = {}
        scopes = await my_scopes()
        for scope in scopes:
            dependent_scopes = scope.get("dependent_scopes")
            dependent_ids = frozenset([sc.get("scope") for sc in dependent_scopes])
            _my_scope_cache[dependent_ids] = scope.get("scope_string")


async def my_scopes():
    scopes = await _perform_auth_request("/scopes", "GET", None)
    return scopes.get("scopes")


async def get_scope_for_dependent_set(
    dependent_scope_strings: List[str],
    scope_name: Optional[str] = None,
    scope_suffix: Optional[str] = None,
) -> str:
    await initialize_scope_cache()
    scope_ids = await lookup_scope_ids(dependent_scope_strings)

    scope_id_set = frozenset(scope_ids.values())
    scope_string = _my_scope_cache.get(scope_id_set)
    if scope_string is not None:
        return scope_string

    has_dependent_scopes = len(dependent_scope_strings) > 0
    if scope_name is None:
        if has_dependent_scopes:
            scope_name = f"Pseudo Trigger using {dependent_scope_strings[0]}"
        else:
            scope_name = "For Pseudo Trigger "
    if scope_suffix is None:
        if has_dependent_scopes:
            replacements = [("-", "_"), ("/", ""), (":", ""), (".", "")]
            scope_suffix = dependent_scope_strings[0].strip().lower()
            for replacement in replacements:
                scope_suffix = scope_suffix.replace(replacement[0], replacement[1])
        else:
            scope_suffix = "pseudo_trigger"
    scope_string = await create_scope(scope_name, scope_suffix, scope_id_set)

    return scope_string


def _dependent_scope_param(dependent_scope_ids: Iterable[str]) -> List[Dict[str, Any]]:
    return [
        {"scope": sid, "optional": False, "requires_refresh_token": True}
        for sid in dependent_scope_ids
    ]


async def create_scope(
    scope_name: str, scope_suffix: str, dependent_scope_ids: Iterable[str]
) -> str:
    params = {
        "scope": {
            "name": scope_name,
            "description": "Run " + scope_name,
            "scope_suffix": scope_suffix,
            "dependent_scopes": _dependent_scope_param(dependent_scope_ids),
        }
    }

    client_id = config.get("CLIENT_ID")
    create_scope_path = f"/clients/{client_id}/scopes"

    create_scope_info = await _perform_auth_request(create_scope_path, "POST", params)

    try:
        return create_scope_info.get("scopes")[0]["scope_string"]
    except KeyError:
        raise HTTPException(
            status_code=500,
            detail=f"Scope creation missing required scope value in {create_scope_info}",
        )


_scope_id_cache = cachetools.TTLCache(maxsize=100, ttl=12 * 60 * 60)


async def lookup_scope_ids(scope_strings: MutableSequence[str]) -> Dict[str, str]:
    """Do an Auth request to lookup a set of scope strings and return back a Dict mapping
    the input scope strings to their ids.
    """
    return_dict: Dict[str, str] = {}
    unknown_scopes = []
    # Check for presence of the desired scope string in the cache and that it has been
    # updated within the last 12 hours. 12 hour policy is pretty much arbitrary.
    for scope_string in scope_strings:
        scope_id = _scope_id_cache.get(scope_string)
        if scope_id is not None:
            return_dict[scope_string] = scope_id
        else:
            unknown_scopes.append(scope_string)
    # We got everything from cache, so we can just return
    if len(unknown_scopes) == 0:
        return return_dict

    unknown_scopes_list = ",".join(unknown_scopes)
    scopes_response = await _perform_auth_request(
        f"/scopes?scope_strings={unknown_scopes_list}", "GET"
    )
    auth_scopes = scopes_response.get("scopes", [])
    for scope in auth_scopes:
        scope_string = scope.get("scope_string")
        scope_id = scope.get("id")
        return_dict[scope_string] = scope_id
        _scope_id_cache[scope_string] = scope_id
    return return_dict

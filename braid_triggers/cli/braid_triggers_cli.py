import json
import os
from typing import Mapping

import typer
from globus_sdk import GlobusAPIError

from braid_triggers.sdk import (
    TriggerClient,
    create_trigger_client,
    get_current_user,
    logout,
    revoke_login,
)

cli_app = typer.Typer()
trigger_app = typer.Typer(name="trigger", short_help="Manage your Triggers")
cli_app.add_typer(trigger_app, name="trigger")

_DEFAULT_BASE_URL = "https://triggers-api.test.triggers.automate.globuscs.info"
BASE_URL = os.environ.get("BRAID_TRIGGERS_URL", _DEFAULT_BASE_URL)
_base_url_argument = typer.Argument(
    _DEFAULT_BASE_URL, envvar="BRAID_TRIGGERS_URL", hidden=True
)
CLI_NATIVE_CLIENT_ID = "1602fba0-9893-49cb-a2fe-aa064b452462"
MANAGE_TRIGGERS_SCOPE = (
    "https://auth.globus.org/scopes/"
    "5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"
)

verbosity_option = typer.Option(
    False, "--verbose", "-v", help="Run with increased verbosity", show_default=False
)


def echo_json(json_map: Mapping) -> None:
    out = json.dumps(json_map, indent=2)
    typer.echo(out, color=typer.colors.GREEN)


def echo_error(err: GlobusAPIError) -> None:
    typer.echo(err.message, color=typer.colors.RED)


def _string_or_file(in_str: str) -> str:
    try:
        with open(in_str, "r") as f:
            in_str = f.read()
    except Exception:
        pass  # We assume it isn't a file and go on with our lives
    return in_str


def _get_trigger_client(base_url: str) -> TriggerClient:
    return create_trigger_client(CLI_NATIVE_CLIENT_ID, base_url)


@trigger_app.command()
def create(
    queue_id: str = typer.Option(...),
    action_url: str = typer.Option(...),
    event_filter: str = typer.Option(
        "True",
        callback=_string_or_file,
        help=(
            "An expression to be matched against the properties of an incoming "
            "Event to determine if an Action invocation should be performed."
        ),
    ),
    event_template: str = typer.Option(
        ...,
        callback=_string_or_file,
        help=(
            "The template transforming the fields of the incoming Event into "
            "fields for the Body fo the Action invocation."
        ),
    ),
    action_scope: str = typer.Option(
        "",
        help=(
            "Optionally provide the scope for the action to be invoked. "
            "If not provided, it will be determined by introspecting the action-url."
        ),
        show_default=False,
    ),
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.create(
            queue_id, action_url, event_filter, event_template, action_scope
        )
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


@trigger_app.command()
def display(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.lookup(trigger_id)
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


@trigger_app.command()
def list(
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.list()
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


@trigger_app.command()
def enable(
    scope: str = typer.Option(None),
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.enable(trigger_id, scope=scope)
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


@trigger_app.command()
def disable(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.disable(trigger_id)
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


@trigger_app.command()
def delete(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    tc = _get_trigger_client(base_url)
    try:
        resp = tc.remove(trigger_id)
        echo_json(resp.data)
    except GlobusAPIError as gae:
        echo_error(gae)


session_app = typer.Typer(
    name="session", short_help="Manage your session with the Triggers Command Line"
)


@session_app.command("whoami")
def session_whoami(verbose: bool = verbosity_option):
    user = get_current_user()
    if verbose:
        echo_json(user)
    else:
        output = user["preferred_username"]
    typer.secho(output, fg=typer.colors.GREEN)


@session_app.command("logout")
def session_logout():
    logout()
    typer.secho("Logged Out", fg=typer.colors.GREEN)


@session_app.command("revoke")
def session_revoke():
    revoke_login()
    typer.secho("All stored consents have been revoked", fg=typer.colors.GREEN)


cli_app.add_typer(session_app)


def main():
    cli_app()


if __name__ == "__main__":
    main()

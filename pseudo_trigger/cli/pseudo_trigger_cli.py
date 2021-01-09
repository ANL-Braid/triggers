import json
import os
from typing import Mapping

import requests
import typer
from globus_automate_client import create_flows_client

from .token_management import get_authorization_header_for_scope

app = typer.Typer()
trigger_app = typer.Typer(name="trigger")
app.add_typer(trigger_app, name="trigger")

_DEFAULT_BASE_URL = "http://localhost:5001/triggers"
BASE_URL = os.environ.get("PSEUDO_TRIGGER_URL", _DEFAULT_BASE_URL)
_base_url_argument = typer.Argument(
    _DEFAULT_BASE_URL, envvar="PSEUDO_TRIGGER_URL", hidden=True
)
CLI_NATIVE_CLIENT_ID = "1602fba0-9893-49cb-a2fe-aa064b452462"
MANAGE_TRIGGERS_SCOPE = "https://auth.globus.org/scopes/5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"


def echo_json(json_map: Mapping) -> None:
    out = json.dumps(json_map, indent=2)
    typer.echo(out)


def _string_or_file(in_str: str) -> str:
    try:
        with open(in_str, "r") as f:
            in_str = f.read()
    except Exception:
        pass  # We assume it isn't a file and go on with our lives
    return in_str


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
    body = {
        "queue_id": queue_id,
        "action_url": action_url,
        "event_filter": event_filter,
    }
    body["event_template"] = json.loads(event_template)
    if action_scope:
        body["action_scope"] = action_scope
    elif action_url.startswith("https://flows.globus.org"):
        # If the action url is for the flows service, we will attempt to do a lookup in
        # the flows service, but that requires authentication
        fc = create_flows_client(CLI_NATIVE_CLIENT_ID)
        _, flow_id = action_url.rsplit("/", 1)
        print(f"Retrieving scope for Flow id: {flow_id}...")
        flow_description = fc.get_flow(flow_id)
        action_scope = flow_description.get("globus_auth_scope")
        if action_scope:
            typer.echo(f"Scope is {action_scope}")
            body["action_scope"] = action_scope
        else:
            typer.echo(f"Failed to get scope")
            raise typer.Exit(code=1)

    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.post(base_url, json=body, headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def display(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.get(f"{base_url}/{trigger_id}", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def list(
    base_url: str = _base_url_argument,
):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.get(f"{base_url}", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def enable(
    scope: str = typer.Option(None),
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    if scope is None:
        get_resp = requests.get(f"{base_url}/{trigger_id}")
        if get_resp.status_code == 200:
            scope = get_resp.json().get("globus_auth_scope")

    auth_header = get_authorization_header_for_scope(scope, CLI_NATIVE_CLIENT_ID)
    resp = requests.post(f"{base_url}/{trigger_id}/enable", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def disable(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.post(f"{base_url}/{trigger_id}/disable", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def delete(
    trigger_id: str = typer.Argument(...),
    base_url: str = _base_url_argument,
):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.delete(f"{base_url}/{trigger_id}", headers=auth_header)
    echo_json(resp.json())


def main():
    app()


if __name__ == "__main__":
    main()

import json
from typing import Mapping

import requests
import typer

from .token_management import get_authorization_header_for_scope

app = typer.Typer()
trigger_app = typer.Typer(name="trigger")
app.add_typer(trigger_app, name="trigger")

BASE_URL = "http://localhost:5001/triggers"

CLI_NATIVE_CLIENT_ID = "1602fba0-9893-49cb-a2fe-aa064b452462"
MANAGE_TRIGGERS_SCOPE = "https://auth.globus.org/scopes/5292be17-96f0-4ab6-957a-ecd516a1759e/manage_triggers"


def echo_json(json_map: Mapping) -> None:
    out = json.dumps(json_map, indent=2)
    typer.echo(out)


@trigger_app.command()
def create(
    queue_id: str = typer.Option(...),
    action_url: str = typer.Option(...),
    event_filter: str = typer.Option(...),
    event_template: str = typer.Option(...),
):
    body = {
        "queue_id": queue_id,
        "action_url": action_url,
        "event_filter": event_filter,
    }
    body["event_template"] = json.loads(event_template)
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.post(BASE_URL, json=body, headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def display(trigger_id: str = typer.Argument(...)):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.get(f"{BASE_URL}/{trigger_id}", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def enable(scope: str = typer.Option(None), trigger_id: str = typer.Argument(...)):
    if scope is None:
        get_resp = requests.get(f"{BASE_URL}/{trigger_id}")
        if get_resp.status_code == 200:
            scope = get_resp.json().get("globus_auth_scope")
    auth_header = get_authorization_header_for_scope(scope, CLI_NATIVE_CLIENT_ID)

    resp = requests.post(f"{BASE_URL}/{trigger_id}/enable", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def disable(trigger_id: str = typer.Argument(...)):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.post(f"{BASE_URL}/{trigger_id}/disable", headers=auth_header)
    echo_json(resp.json())


@trigger_app.command()
def delete(trigger_id: str = typer.Argument(...)):
    auth_header = get_authorization_header_for_scope(
        MANAGE_TRIGGERS_SCOPE, CLI_NATIVE_CLIENT_ID
    )
    resp = requests.delete(f"{BASE_URL}/{trigger_id}", headers=auth_header)
    echo_json(resp.json())


def main():
    app()


if __name__ == "__main__":
    main()

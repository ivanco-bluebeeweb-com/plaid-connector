"""The single 'App settings' screen (center slot) -- connection management
(disconnect per Plaid connection) for Plaid Connector. Split out of
panels.py per the same convention as Stripe Connector's / MuleSoft
Connector's panels_settings.py.

Per ~/UI_INTERFACE_STANDARD.md: the left sidebar never wraps the connect
form in a Card, and disconnect (never exposed in the sidebar itself) lives
here, one row per connected Plaid connection, showing which environments
(Sandbox/Production) each one has a working secret for. The one secondary
"App settings" button sits LAST at the bottom of the sidebar.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("id", "")
    envs = []
    if c.get("sandbox_secret"):
        envs.append("Sandbox")
    if c.get("production_secret"):
        envs.append("Production")
    envs_text = " + ".join(envs) if envs else "No environment configured"
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(envs_text, variant="caption"),
        ui.Button(
            "Disconnect", variant="danger", size="sm",
            on_click=ui.Call("disconnect_plaid", {"connection_id": c.get("id")}),
        ),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Stack(direction="v", gap=1, children=[
            ui.Text("Connections", variant="heading"),
            ui.Text("No Plaid accounts connected yet.", variant="caption"),
        ])
    children: list[ui.UINode] = [ui.Text("Connections", variant="heading")]
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=3, align="stretch", children=children)


@ext.panel("plaid_settings", slot="center", title="Plaid settings")
async def plaid_settings_panel(ctx, **kwargs) -> object:
    connections = await h._get_connections(ctx)
    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        ui.Header(text="Plaid settings", level=2,
                   subtitle="Manage your connected Plaid accounts"),
        _connections_section(connections),
    ])

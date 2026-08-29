"""Panel UI -- connections list/connect form in the sidebar.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as Stripe
Connector's / MuleSoft Connector's panels.py).

Every section (connections, connect form) is a plain ui.Stack, content
stacked vertically and left-aligned, sections separated by ui.Divider()
-- no Card border/background/shadow anywhere in this slot. Disconnect
lives only in the "App settings" screen (panels_settings.py). The one
secondary "App settings" button is always the LAST element at the
bottom of the sidebar.

WHY client_id + TWO OPTIONAL SECRET FIELDS, NOT ONE KEY FIELD LIKE
STRIPE's.

Plaid's auth model is client_id shared + a DIFFERENT secret per
environment (see app.py's module docstring) -- the connect form must
let a user paste either or both secrets in one submission instead of
forcing two separate "connect" actions for one Plaid account.

WHY THE FORM IS FULL-WIDTH AND EVERY INPUT HAS A LABEL.

Per ~/UI_INTERFACE_STANDARD.md (updated after the MuleSoft/Cin7/
ShipStation review): every input must carry its own ui.Text label (never
rely on the placeholder alone), placeholders must be contextually
realistic examples (not generic "Enter value"), and the ui.Form container
itself must be forced to the full width of the left sidebar with its
children stretched to fill it -- align="stretch" on every wrapping Stack.

WHY THE "HOW DO I SET THIS UP?" WALKTHROUGH LIVES ONLY IN THE MODAL.

Per the same standard: once a button+modal pair exists for a
walkthrough, the sidebar must not duplicate that instruction text
inline -- so this sidebar carries no explanatory paragraph, only the
button that opens plaid_connect_help.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers as h


def _settings_button() -> ui.UINode:
    return ui.Button(
        "App settings", variant="secondary", size="sm",
        icon="settings", on_click=ui.Call("__panel__plaid_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("id", "")
    envs = []
    if c.get("has_sandbox"):
        envs.append("Sandbox")
    if c.get("has_production"):
        envs.append("Production")
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(" + ".join(envs) or "No secrets saved", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No Plaid accounts connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Plain content, no Card wrapper. Form is forced full-width per
    UI_INTERFACE_STANDARD.md; every field carries its own label plus a
    contextually realistic placeholder. No walkthrough text here -- it
    lives only in plaid_connect_help's modal."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__plaid_connect_help")),
        ui.Form(
            action="connect_plaid",
            submit_label="Verify and connect",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Client ID", variant="caption"),
                    ui.Input(param_name="client_id",
                              placeholder="5f8a2c1e9b0d3a0012f4b6a7"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Sandbox secret (optional)", variant="caption"),
                    ui.Password(param_name="sandbox_secret",
                                 placeholder="Paste your Sandbox secret to test with fake bank data"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Production secret (optional)", variant="caption"),
                    ui.Password(param_name="production_secret",
                                 placeholder="Paste your Production secret for real bank data"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label",
                              placeholder="e.g. Main fintech app"),
                ]),
            ],
        ),
    ])


@ext.panel("plaid_connect", slot="left", title="Plaid", icon="🏦",
           default_width=320, min_width=260, max_width=420)
async def plaid_connect_panel(ctx, **kwargs) -> object:
    connections = await h._get_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="Plaid", level=2,
                        subtitle="Manage your Plaid bank-data account from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected accounts", variant="subtitle"),
        _connections_section(connections),
        ui.Divider(),
        ui.Button("View account overview", variant="primary", size="sm", full_width=True,
                  icon="Landmark", on_click=ui.Call("__panel__plaid_center")),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("plaid_connect_help", slot="center",
           title="How to connect Plaid", center_overlay=True)
async def plaid_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. In the Plaid Dashboard, open Team Settings > Keys."),
        ui.Text("2. Copy your client_id -- it is the same value for both Sandbox and Production."),
        ui.Text("3. Copy your Sandbox secret if you want to test with fake bank data (free, no real accounts), and/or your Production secret for real bank data (billed by Plaid)."),
        ui.Text("4. Paste them below. A Sandbox secret only works against Sandbox, a Production secret only works against Production -- they are never interchangeable."),
        ui.Divider(),
        ui.Alert(
            title="Your keys, your account",
            message=(
                "client_id and secrets are encrypted and used only to call "
                "the Plaid API on your behalf, against your own Plaid "
                "account and your own billing."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link(
            label="Open Plaid's official API keys guide",
            href="https://plaid.com/docs/api/",
        ),
    ])
    return ui.Dialog(
        title="How to connect Plaid",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


@ext.panel("plaid_center", slot="center", title="Plaid", icon="🏦", center_overlay=True)
async def plaid_center_panel(ctx, **kwargs) -> object:
    """Base center panel -- per UI_INTERFACE_STANDARD.md (2026-08-20).
    This app has no list/detail content of its own to show in the center
    by default (everything lives in the sidebar). MUST carry
    center_overlay=True: per docs.imperal.io/en/concepts/panels, a plain
    slot="center" panel is registered but the Panel app never fetches it
    at session-init without that flag. Text is the shared canonical
    wording -- must stay identical across every app in this situation."""
    connections = await h._get_connections(ctx)
    if not connections:
        return ui.Empty(message="Connect a Plaid account from the sidebar to see it here.", icon="🏦")

    from schemas import ListAvailableProductsParams
    result = await h.list_available_products(ctx, ListAvailableProductsParams())
    body: list[ui.UINode] = [ui.Text("Account overview", variant="subtitle")]
    body.append(ui.Stats(children=[
        ui.Stat(label="Connected accounts", value=str(len(connections))),
    ]))
    for c in connections:
        envs = []
        if c.get("has_sandbox"):
            envs.append("Sandbox")
        if c.get("has_production"):
            envs.append("Production")
        body.append(ui.Stack(direction="h", gap=2, align="center", children=[
            ui.Badge(label=" + ".join(envs) or "No secrets", color="green" if envs else "gray"),
            ui.Text(c.get("label") or c.get("id", ""), variant="body"),
        ]))

    body.append(ui.Divider())
    body.append(ui.Text("Available products", variant="subtitle"))
    if result.success and result.data:
        products = result.data if isinstance(result.data, list) else [result.data]
        for p in products[:15]:
            name = p.get("product") if isinstance(p, dict) else str(p)
            desc = p.get("description", "") if isinstance(p, dict) else ""
            body.append(ui.Stack(direction="v", gap=0, align="stretch", children=[
                ui.Text(f"• {name}", variant="body"),
                ui.Text(desc, variant="caption"),
            ]))
    else:
        body.append(ui.Text("Could not load the product list.", variant="caption"))

    return ui.Stack(direction="v", gap=3, align="stretch", children=body)

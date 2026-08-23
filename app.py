"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as Stripe Connector /
MuleSoft Connector / DataForSEO Connector. Plaid brokers access to real
end users' real bank accounts -- Imperal cannot and should not sit as a
shared intermediary for that. The user pastes their own Plaid client_id
plus per-environment secret(s) once, Vault-encrypted via `ctx.secrets`,
and every call runs against their own Plaid account and their own
Plaid billing.

WHY client_id + secret(s), NOT OAUTH2.

Plaid authenticates every API request with `client_id` + `secret` sent
as JSON body fields (plaid.com/docs/api/, confirmed 2026-08-22) -- there
is no OAuth dance for the developer managing their OWN Plaid account.
(Plaid Link itself uses an OAuth-like consent flow for the END USER's
bank login, but that happens entirely client-side in the Link SDK and
never touches this connector's own auth model.)

WHY TWO SEPARATE SECRET SLOTS PER CONNECTION (sandbox_secret /
production_secret), NOT ONE.

Plaid issues one client_id per account but a DIFFERENT secret per
environment (plaid.com/blog/api-secrets/, confirmed 2026-08-22) -- a
Sandbox secret is rejected by production.plaid.com and vice versa.
Modeling this as a single opaque "secret" field would either force the
user to maintain two separate connections for the same Plaid account
(confusing, since Items/data differ but the account/billing is one), or
silently drop one environment. Instead each stored connection carries
both slots, either of which may be blank.

WHY `write_mode="both"`, SAME REASONING AS STRIPE/MULESOFT/APPFOLIO.

Declaring `write_mode="user"` would mean only the platform's generic
Secrets screen could write this -- leaving a first-time user with no
in-app screen explaining what a Plaid client_id/secret even is or
whether what they pasted actually works. `"both"` keeps the generic
Secrets screen as a fallback while letting `connect_plaid` validate the
credentials against Plaid's own API (`/institutions/get` with count=1)
*before* writing them.

WHY ONE SECRET HOLDING A JSON ARRAY (multi-account), SAME PRECEDENT AS
STRIPE CONNECTOR / MULESOFT CONNECTOR / POWER AUTOMATE CONNECTOR.

A user may reasonably run more than one Plaid account (e.g. one for a
side project, one for a client). `ctx.secrets` only supports a fixed,
manifest-declared set of NAMES -- there is no "one secret per
connection_id" primitive. `plaid_connections` holds a JSON array of
`{id, label, client_id, sandbox_secret, production_secret}` objects;
`schemas.py`'s `connection_id` parameter on every tool call addresses
one specific entry -- see handlers.py's `_load_connections`/
`_save_connections`.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "plaid-connector",
    version="0.1.0",
    display_name="Plaid",
    description=(
        "Connect your own Plaid account (Sandbox and/or Production) to "
        "link end users' bank accounts and read/act on their financial "
        "data from Imperal -- Link tokens, Items, Accounts, "
        "Institutions, Transactions (sync + enrich), Auth, Identity, "
        "Investments, Liabilities, Assets (reports), Income, Transfer "
        "(ACH/RTP/wire), Signal (return-risk scoring), Monitor "
        "(watchlist screening), processor tokens, plus Sandbox testing "
        "helpers and value-add reports (net worth, spending overview, "
        "recurring charges, low-balance alerts, Item health audit). "
        "Nothing is hosted or proxied by Imperal beyond the request "
        "itself -- your credentials, your Plaid account, your billing."
    ),
    icon="icon.svg",
    capabilities=[
        "plaid:read",
        "plaid:write",
    ],
    actions_explicit=True,
    system=False,
)

chat = ChatExtension(
    ext,
    tool_name="plaid",
    description=(
        "Plaid Connector -- connect your own Plaid account, then create "
        "Link tokens, manage Items/Accounts, read Transactions/Auth/"
        "Identity/Investments/Liabilities, build Asset Reports, verify "
        "Income, move money via Transfer, score ACH risk via Signal, "
        "screen watchlists via Monitor, and run Sandbox tests."
    ),
)

ext.secret(
    "plaid_connections",
    (
        "Your connected Plaid accounts -- stored as a JSON array, one "
        "entry per account, each with its own client_id plus "
        "sandbox_secret and/or production_secret. Managed through "
        "connect_plaid / disconnect_plaid -- you should not need to "
        "edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=90,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one Plaid account connection is stored, same shape as Stripe
    Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("plaid_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} Plaid account(s) connected." if count
            else "Not connected yet -- run connect_plaid."
        ),
    }

"""Thin HTTP client for the Plaid REST API.

WHY `ctx.http.post(...)`, NOT A HAND-ROLLED HTTP CLIENT CLASS.

Confirmed by reading the real installed imperal_sdk (2026-08-22, same SDK
used by Stripe Connector / MuleSoft Connector / Cin7 Core Connector):
`Context.http` is an `HTTPProtocol` exposing `get/post/put/patch/delete(url,
**kwargs) -> HTTPResponse`, where `HTTPResponse` has `.status_code`,
`.json()`, `.text()`. There is NO `imperal_sdk.HTTPClient` class -- an
earlier draft of this file assumed one (`HTTPClient(base_url=..., ...)`)
and would have crashed on the very first real call with ImportError. Every
wrapper below takes `ctx` explicitly and calls `ctx.http.post(...)`, same
shape as stripe_client.py's `_request()`.

WHY TWO ENVIRONMENTS, NOT THREE (Development retired).

Plaid used to offer Sandbox / Development / Production. Development was
decommissioned 2024-06-20 (plaid.com/docs/quickstart/glossary/, confirmed
2026-08-22) -- every Development Item was force-migrated or removed. This
connector therefore only ever models two environments: `sandbox`
(https://sandbox.plaid.com, fake data, free) and `production`
(https://production.plaid.com, real bank data, billed). There is no
`development` value anywhere in this codebase on purpose -- if it shows up
again it is a regression, not a missing feature.

WHY client_id IS SHARED BUT secret IS PER-ENVIRONMENT.

Plaid issues one client_id per Plaid account but a DIFFERENT `secret` per
environment (plaid.com/blog/api-secrets/, plaid.com/docs/api/, confirmed
2026-08-22) -- a Sandbox secret never works against production.plaid.com
and vice versa. Items created in one environment cannot move to the
other. `handlers.py`'s stored connection therefore keeps client_id once
and up to two secrets (sandbox_secret / production_secret), and every
call states which environment it targets.

WHY A SINGLE `request()` FOR EVERY ENDPOINT, NOT ONE METHOD PER ENDPOINT.

Plaid's whole API is POST-only JSON-body (no query strings, no path
params beyond the fixed route) -- client_id/secret/access_token are just
extra keys in the same JSON body as everything else. A single generic
`request(ctx, ..., path, body)` that merges in client_id+secret is exactly
as safe as 80 hand-written wrappers and avoids 80 near-duplicate methods;
handlers.py supplies the per-endpoint body shape via typed Pydantic params.

WHY ERRORS ARE RAISED AS `ClientFail`, NOT RETURNED.

Same pattern as every other connector's client module in this portfolio
(Cin7 Core, PagerDuty, AppFolio): handlers.py wraps each call in
try/except ClientFail and turns it into ActionResult.error with Plaid's
own honest error_message/display_message -- never a made-up one.
"""
from __future__ import annotations

import json
from typing import Any

SANDBOX_BASE = "https://sandbox.plaid.com"
PRODUCTION_BASE = "https://production.plaid.com"

ENVIRONMENTS = ("sandbox", "production")


class ClientFail(Exception):
    """Raised for any Plaid API error -- handlers.py maps this to
    ActionResult.error with the honest message Plaid returned, same
    pattern as every other connector's ClientFail in this portfolio."""

    def __init__(self, message: str, *, error_code: str = "", error_type: str = "", status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.error_type = error_type
        self.status_code = status_code


def base_url_for(environment: str) -> str:
    if environment == "sandbox":
        return SANDBOX_BASE
    if environment == "production":
        return PRODUCTION_BASE
    raise ClientFail(
        f"Unknown Plaid environment '{environment}'. Only 'sandbox' and "
        "'production' exist -- Plaid retired 'development' in 2024."
    )


async def request(
    ctx,
    *,
    client_id: str,
    secret: str,
    environment: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST one Plaid endpoint through `ctx.http`. `path` is like
    '/accounts/get'. Merges client_id/secret into the JSON body (Plaid's
    own convention -- there is no separate auth header). Raises
    ClientFail on any non-2xx or Plaid-shaped error envelope."""
    base = base_url_for(environment)
    url = f"{base}{path}"
    payload = dict(body or {})
    payload["client_id"] = client_id
    payload["secret"] = secret

    try:
        resp = await ctx.http.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 -- network-level failure, not a Plaid error
        raise ClientFail(f"Network error calling Plaid {path}: {exc}") from exc

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {}

    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error_code")):
        message = (
            (data.get("error_message") if isinstance(data, dict) else "")
            or (data.get("display_message") if isinstance(data, dict) else "")
            or resp.text()
            or f"Plaid returned HTTP {resp.status_code} for {path}"
        )
        raise ClientFail(
            message,
            error_code=str(data.get("error_code") or "") if isinstance(data, dict) else "",
            error_type=str(data.get("error_type") or "") if isinstance(data, dict) else "",
            status_code=resp.status_code,
        )

    if not isinstance(data, dict):
        raise ClientFail(f"Plaid returned an unexpected non-object response for {path}")

    return data


def message_for(exc: ClientFail) -> str:
    """Human-readable one-liner for chat/panel surfaces -- mirrors the
    message_for() helper pattern used by AppFolio Connector's client."""
    parts = [exc.message]
    if exc.error_code:
        parts.append(f"(error_code={exc.error_code})")
    return " ".join(parts)

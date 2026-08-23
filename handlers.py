"""Chat functions for Plaid Connector: connection management, Link tokens,
Items, Accounts, Institutions, Transactions, Auth, Identity, Investments,
Liabilities, Assets (reports), Income, Transfer, Signal, Monitor
(watchlist screening), processor tokens, Sandbox helpers, and Tier-3
value-add reports. Built on plaid_client.py / schemas.py, following the
same shape as Stripe Connector's / AppFolio Connector's handlers.py.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult, sdl

import plaid_client as pc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectPlaidParams, ConnectionIdParam, DisconnectPlaidParams,
    ListConnectionsParams, PlaidConnectionEntity,
    CreateLinkTokenParams, GetLinkTokenParams, ExchangePublicTokenParams,
    ItemActionParams, RemoveItemParams, GetItemParams,
    UpdateItemWebhookParams, CreatePublicTokenParams,
    GetAccountsParams, GetInstitutionParams, ListInstitutionsParams,
    SearchInstitutionsParams,
    SyncTransactionsParams, GetTransactionsParams, RefreshTransactionsParams,
    GetRecurringTransactionsParams, EnrichTransactionsParams,
    GetAuthParams, GetIdentityParams, MatchIdentityParams,
    GetHoldingsParams, GetInvestmentTransactionsParams,
    RefreshInvestmentsParams, GetLiabilitiesParams,
    CreateAssetReportParams, GetAssetReportParams, GetAssetReportPdfParams,
    RefreshAssetReportParams, FilterAssetReportParams,
    RemoveAssetReportParams, CreateAuditCopyParams, RemoveAuditCopyParams,
    CreateIncomeVerificationParams, GetIncomeVerificationParams,
    GetBankIncomeParams,
    CreateTransferAuthorizationParams, CreateTransferParams,
    GetTransferParams, ListTransfersParams, CancelTransferParams,
    CreateTransferRefundParams, ListTransferEventsParams,
    EvaluateSignalParams, ReportSignalDecisionParams,
    CreateWatchlistScreeningParams, GetWatchlistScreeningParams,
    ListWatchlistScreeningsParams, ReviewWatchlistScreeningParams,
    CreateProcessorTokenParams, CreateBankAccountTokenParams,
    CreateSandboxPublicTokenParams,
    FireSandboxWebhookParams, ResetSandboxItemLoginParams,
    SetSandboxVerificationStatusParams, CreateSandboxTransactionsParams,
    AuditItemHealthParams, GetSpendingOverviewParams,
    DetectRecurringChargesParams, GetNetWorthSnapshotParams,
    CheckLowBalanceRiskParams, ListAvailableProductsParams,
    PlaidItemEntity, PlaidAccountEntity, PlaidInstitutionEntity,
)

_SECRET_NAME = "plaid_connections"


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def _get_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _resolve_connection(ctx, connection_id: str = "") -> dict | None:
    """Resolve a connection_id (or the sole connection) to its stored dict.
    Returns None if not found, or if more than one exists and none was
    specified (caller must then ask the user to disambiguate)."""
    connections = await _get_connections(ctx)
    if not connections:
        return None
    if connection_id:
        for c in connections:
            if c.get("id") == connection_id:
                return c
        return None
    if len(connections) == 1:
        return connections[0]
    return None


def _secret_for(conn: dict, environment: str) -> str:
    if environment == "sandbox":
        return conn.get("sandbox_secret", "")
    if environment == "production":
        return conn.get("production_secret", "")
    return ""


def _err(e: pc.ClientFail) -> ActionResult:
    return ActionResult.error(
        pc.message_for(e),
        e.status_code >= 500 or e.status_code == 429,
        code=e.error_code or "UNKNOWN",
    )


def _no_connection_error(connection_id: str, connections: list[dict]) -> ActionResult:
    if not connections:
        return ActionResult.error(
            "No Plaid account connected yet. Run connect_plaid first.",
            code="NOT_CONNECTED",
        )
    if connection_id:
        return ActionResult.error(
            f"No connection found with id '{connection_id}'.", code="NOT_FOUND",
        )
    return ActionResult.error(
        "More than one Plaid connection exists -- pass connection_id to pick one.",
        code="AMBIGUOUS_CONNECTION",
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "connect_plaid",
    "Connect your own Plaid account by saving your client_id plus a Sandbox and/or Production secret, after checking whichever ones you provide actually work. Find these in Plaid Dashboard > Team Settings > Keys.",
    action_type="write",
    effects=["plaid.provider.connected"],
    event="plaid-connector.connect_plaid",
    data_model=PlaidConnectionEntity,
)
async def connect_plaid(ctx, params: ConnectPlaidParams) -> ActionResult:
    if not params.client_id:
        return ActionResult.error("client_id is required.", code="INVALID_REQUEST")
    if not params.sandbox_secret and not params.production_secret:
        return ActionResult.error(
            "Provide at least one secret (sandbox_secret or production_secret).",
            code="INVALID_REQUEST",
        )

    checked_envs = []
    for env, secret in (("sandbox", params.sandbox_secret), ("production", params.production_secret)):
        if not secret:
            continue
        try:
            await pc.request(ctx=ctx, client_id=params.client_id, secret=secret,
                              environment=env, path="/institutions/get",
                              body={"count": 1, "offset": 0, "country_codes": ["US"]})
        except pc.ClientFail as e:
            return ActionResult.error(
                f"{env.capitalize()} secret rejected: {pc.message_for(e)}",
                code=e.error_code or "TOKEN_REJECTED",
            )
        checked_envs.append(env)

    connections = await _get_connections(ctx)
    conn = {
        "id": str(uuid.uuid4()),
        "client_id": params.client_id,
        "sandbox_secret": params.sandbox_secret,
        "production_secret": params.production_secret,
        "label": params.label or "Plaid",
        "connected_at": _now_iso(),
    }
    connections.append(conn)
    await _save_connections(ctx, connections)

    entity = PlaidConnectionEntity(
        id=conn["id"], title=conn["label"],
        label=conn["label"],
        has_sandbox=bool(params.sandbox_secret),
        has_production=bool(params.production_secret),
    )
    return ActionResult.success(
        entity, f"Connected Plaid ({', '.join(checked_envs)}).",
        refresh_panels=["plaid_connect", "plaid_settings"],
    )


@chat.function(
    "disconnect_plaid",
    "Disconnect a Plaid account: deletes the saved client_id/secrets. Nothing in Plaid itself is changed; existing Items keep working if you reconnect the same credentials later.",
    action_type="write",
    effects=["plaid.provider.disconnected"],
    event="plaid-connector.disconnect_plaid",
)
async def disconnect_plaid(ctx, params: DisconnectPlaidParams) -> ActionResult:
    connections = await _get_connections(ctx)
    if not connections:
        return ActionResult.error("No Plaid account connected.", code="NOT_CONNECTED")
    if params.connection_id:
        remaining = [c for c in connections if c.get("id") != params.connection_id]
        if len(remaining) == len(connections):
            return ActionResult.error(f"No connection found with id '{params.connection_id}'.", code="NOT_FOUND")
    elif len(connections) == 1:
        remaining = []
    else:
        return ActionResult.error(
            "More than one Plaid connection exists -- pass connection_id to pick one.",
            code="AMBIGUOUS_CONNECTION",
        )
    await _save_connections(ctx, remaining)
    return ActionResult.success(
        {"disconnected": True}, "Plaid account disconnected.",
        refresh_panels=["plaid_connect", "plaid_settings"],
    )


@chat.function(
    "list_connections",
    "List the connected Plaid accounts.",
    action_type="read",
)
async def list_connections(ctx, params: ListConnectionsParams) -> ActionResult:
    connections = await _get_connections(ctx)
    entities = [
        PlaidConnectionEntity(
            id=c["id"], title=c.get("label", "Plaid"), label=c.get("label", ""),
            has_sandbox=bool(c.get("sandbox_secret")),
            has_production=bool(c.get("production_secret")),
        )
        for c in connections
    ]
    return ActionResult.success(entities, f"{len(entities)} Plaid connection(s).")


# ──────────────────────────────────────────────────────────────────────────
# Link (Link tokens -- Plaid Link itself is rendered client-side, not here)
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "create_link_token",
    "Create a Link token so your app can launch Plaid Link for an end user to connect their bank account (or reauthenticate an existing one in update mode, via access_token).",
    action_type="write",
    effects=["plaid.link_token.created"],
    event="plaid-connector.create_link_token",
)
async def create_link_token(ctx, params: CreateLinkTokenParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(
            f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED",
        )
    body = {
        "client_name": params.client_name,
        "language": params.language,
        "country_codes": params.country_codes,
        "user": {"client_user_id": params.client_user_id},
    }
    if params.access_token:
        body["access_token"] = params.access_token
    else:
        body["products"] = params.products
    if params.redirect_uri:
        body["redirect_uri"] = params.redirect_uri
    if params.webhook:
        body["webhook"] = params.webhook
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/link/token/create", body=body)
    except pc.ClientFail as e:
        return _err(e)
    return ActionResult.success(
        {"link_token": data.get("link_token"), "expiration": data.get("expiration"),
         "request_id": data.get("request_id")},
        "Link token created -- pass it to Plaid Link on your frontend.",
    )


@chat.function(
    "get_link_token",
    "Read a Link token's own metadata (status, products requested) -- useful to confirm what a token was configured for before handing it to a client.",
    action_type="read",
)
async def get_link_token(ctx, params: GetLinkTokenParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/link/token/get",
                                 body={"link_token": params.link_token})
    except pc.ClientFail as e:
        return _err(e)
    return ActionResult.success(data, "Link token metadata retrieved.")


@chat.function(
    "exchange_public_token",
    "Exchange a public_token (returned by Plaid Link after an end user finishes connecting their bank) for a permanent access_token identifying the new Item. Store the access_token yourself -- Plaid never lets you retrieve it again.",
    action_type="write",
    effects=["plaid.item.created"],
    event="plaid-connector.exchange_public_token",
    data_model=PlaidItemEntity,
)
async def exchange_public_token(ctx, params: ExchangePublicTokenParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/item/public_token/exchange",
                                 body={"public_token": params.public_token})
    except pc.ClientFail as e:
        return _err(e)
    entity = PlaidItemEntity(
        id=data.get("item_id", ""), title=data.get("item_id", "Plaid Item"),
        environment=params.environment,
    )
    return ActionResult.success(
        {"access_token": data.get("access_token"), "item_id": data.get("item_id"),
         "request_id": data.get("request_id")},
        "Item created -- store this access_token yourself, Plaid will not show it again.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Items
# ──────────────────────────────────────────────────────────────────────────


async def _item_call(ctx, params: ItemActionParams, path: str, extra: dict | None = None) -> tuple[dict | None, ActionResult | None]:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return None, _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return None, ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    body = {"access_token": params.access_token}
    if extra:
        body.update(extra)
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path=path, body=body)
    except pc.ClientFail as e:
        return None, _err(e)
    return data, None


@chat.function("get_item", "Read one Plaid Item in full: institution, available/billed products, and error state.", action_type="read")
async def get_item(ctx, params: GetItemParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/item/get")
    if err:
        return err
    item = data.get("item", {})
    entity = PlaidItemEntity(
        id=item.get("item_id", ""), title=item.get("institution_id", "Plaid Item") or "Plaid Item",
        institution_id=item.get("institution_id") or "", environment=params.environment,
        available_products=item.get("available_products", []),
        billed_products=item.get("billed_products", []),
    )
    return ActionResult.success(entity, "Item retrieved.")


@chat.function(
    "remove_item",
    "Permanently remove a Plaid Item, revoking its access_token. Cannot be undone -- the end user would need to reconnect through Link again.",
    action_type="write",
    effects=["plaid.item.removed"],
    event="plaid-connector.remove_item",
)
async def remove_item(ctx, params: RemoveItemParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/item/remove")
    if err:
        return err
    return ActionResult.success({"removed": True}, "Item removed.")


@chat.function(
    "update_item_webhook",
    "Change the webhook URL Plaid sends this Item's events to.",
    action_type="write",
    effects=["plaid.item.updated"],
    event="plaid-connector.update_item_webhook",
)
async def update_item_webhook(ctx, params: UpdateItemWebhookParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/item/webhook/update", {"webhook": params.webhook})
    if err:
        return err
    return ActionResult.success({"updated": True}, "Item webhook updated.")


@chat.function(
    "create_public_token",
    "Re-issue a short-lived public_token for an existing Item, so Link can be launched in update mode from a different client than the one that originally created the Item.",
    action_type="write",
    effects=["plaid.public_token.created"],
    event="plaid-connector.create_public_token",
)
async def create_public_token(ctx, params: CreatePublicTokenParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/item/public_token/create")
    if err:
        return err
    return ActionResult.success(data, "Public token created.")


# ──────────────────────────────────────────────────────────────────────────
# Accounts & Institutions
# ──────────────────────────────────────────────────────────────────────────


@chat.function("get_accounts", "Read every account (or a specific subset) attached to a Plaid Item -- balances, type, subtype, mask.", action_type="read")
async def get_accounts(ctx, params: GetAccountsParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/accounts/get", extra)
    if err:
        return err
    entities = []
    for a in data.get("accounts", []):
        bal = a.get("balances", {})
        entities.append(PlaidAccountEntity(
            id=a.get("account_id", ""), title=a.get("name", "Account"),
            official_name=a.get("official_name") or "", type=a.get("type", ""),
            subtype=a.get("subtype") or "", mask=a.get("mask") or "",
            current_balance=bal.get("current"), available_balance=bal.get("available"),
            iso_currency_code=bal.get("iso_currency_code") or "",
        ))
    return ActionResult.success(entities, f"{len(entities)} account(s).")


@chat.function("get_institution", "Read one financial institution known to Plaid by its institution_id -- name, logo, supported products, OAuth requirement.", action_type="read")
async def get_institution(ctx, params: GetInstitutionParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/institutions/get_by_id",
                                 body={"institution_id": params.institution_id, "country_codes": params.country_codes})
    except pc.ClientFail as e:
        return _err(e)
    inst = data.get("institution", {})
    entity = PlaidInstitutionEntity(
        id=inst.get("institution_id", ""), title=inst.get("name", "Institution"),
        country_codes=inst.get("country_codes", []), products=inst.get("products", []),
        oauth=bool(inst.get("oauth")),
    )
    return ActionResult.success(entity, "Institution retrieved.")


@chat.function("list_institutions", "List financial institutions known to Plaid, paginated.", action_type="read")
async def list_institutions(ctx, params: ListInstitutionsParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/institutions/get",
                                 body={"count": params.count, "offset": params.offset, "country_codes": params.country_codes})
    except pc.ClientFail as e:
        return _err(e)
    entities = [
        PlaidInstitutionEntity(id=i.get("institution_id", ""), title=i.get("name", "Institution"),
                                country_codes=i.get("country_codes", []), products=i.get("products", []),
                                oauth=bool(i.get("oauth")))
        for i in data.get("institutions", [])
    ]
    return ActionResult.success(entities, f"{len(entities)} institution(s).")


@chat.function("search_institutions", "Search financial institutions known to Plaid by free-text name, optionally filtered to institutions supporting given products.", action_type="read")
async def search_institutions(ctx, params: SearchInstitutionsParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/institutions/search",
                                 body={"query": params.query, "products": params.products, "country_codes": params.country_codes})
    except pc.ClientFail as e:
        return _err(e)
    entities = [
        PlaidInstitutionEntity(id=i.get("institution_id", ""), title=i.get("name", "Institution"),
                                country_codes=i.get("country_codes", []), products=i.get("products", []),
                                oauth=bool(i.get("oauth")))
        for i in data.get("institutions", [])
    ]
    return ActionResult.success(entities, f"{len(entities)} institution(s) matching '{params.query}'.")


# ──────────────────────────────────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────────────────────────────────


@chat.function(
    "sync_transactions",
    "Fetch new/modified/removed transactions for an Item since a cursor (the recommended way to keep transactions up to date -- pass the returned next_cursor back in on your next call). Leave cursor blank on the very first call to get full history.",
    action_type="read",
)
async def sync_transactions(ctx, params: SyncTransactionsParams) -> ActionResult:
    extra = {"count": params.count}
    if params.cursor:
        extra["cursor"] = params.cursor
    data, err = await _item_call(ctx, params, "/transactions/sync", extra)
    if err:
        return err
    return ActionResult.success(
        {"added": data.get("added", []), "modified": data.get("modified", []),
         "removed": data.get("removed", []), "next_cursor": data.get("next_cursor"),
         "has_more": data.get("has_more", False)},
        f"{len(data.get('added', []))} added, {len(data.get('modified', []))} modified, "
        f"{len(data.get('removed', []))} removed.",
    )


@chat.function("get_transactions", "Fetch transactions for an Item within a date range (legacy endpoint -- prefer sync_transactions for ongoing sync, this is fine for a one-off historical pull).", action_type="read")
async def get_transactions(ctx, params: GetTransactionsParams) -> ActionResult:
    extra = {
        "start_date": params.start_date, "end_date": params.end_date,
        "options": {"count": params.count, "offset": params.offset},
    }
    if params.account_ids:
        extra["options"]["account_ids"] = params.account_ids
    data, err = await _item_call(ctx, params, "/transactions/get", extra)
    if err:
        return err
    return ActionResult.success(
        {"transactions": data.get("transactions", []), "total_transactions": data.get("total_transactions", 0),
         "accounts": data.get("accounts", [])},
        f"{len(data.get('transactions', []))} of {data.get('total_transactions', 0)} transaction(s).",
    )


@chat.function("refresh_transactions", "Ask Plaid to proactively check for new transaction data right now instead of waiting for its normal refresh schedule. Fires a TRANSACTIONS webhook when done.", action_type="write", effects=["plaid.transactions.refresh_requested"], event="plaid-connector.refresh_transactions")
async def refresh_transactions(ctx, params: RefreshTransactionsParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/transactions/refresh")
    if err:
        return err
    return ActionResult.success({"requested": True}, "Refresh requested -- watch for a TRANSACTIONS webhook.")


@chat.function("get_recurring_transactions", "Read Plaid's own detected recurring transaction streams (subscriptions, regular income/bills) for an Item.", action_type="read")
async def get_recurring_transactions(ctx, params: GetRecurringTransactionsParams) -> ActionResult:
    extra = {"account_ids": params.account_ids} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/transactions/recurring/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Recurring transaction streams retrieved.")


@chat.function("enrich_transactions", "Enrich your OWN raw transaction data (not from Plaid) with merchant name, logo, category, and payment channel using Plaid's Transactions Enrich product.", action_type="read")
async def enrich_transactions(ctx, params: EnrichTransactionsParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=params.environment, path="/transactions/enrich",
                                 body={"account_type": params.account_type, "transactions": params.transactions})
    except pc.ClientFail as e:
        return _err(e)
    return ActionResult.success(data, "Transactions enriched.")


# ──────────────────────────────────────────────────────────────────────────
# Auth & Identity
# ──────────────────────────────────────────────────────────────────────────


@chat.function("get_auth", "Read account and routing numbers for an Item's depository accounts -- the core data needed to originate an ACH transfer.", action_type="read")
async def get_auth(ctx, params: GetAuthParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/auth/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Auth (account/routing numbers) retrieved.")


@chat.function("get_identity", "Read the account holder's name, email, phone, and address on file at their bank, for an Item.", action_type="read")
async def get_identity(ctx, params: GetIdentityParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/identity/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Identity data retrieved.")


@chat.function("match_identity", "Check how closely a name/phone/email/address you provide matches the account holder's real identity on file (Identity Match) -- useful for fraud/KYC checks before trusting a linked account.", action_type="read")
async def match_identity(ctx, params: MatchIdentityParams) -> ActionResult:
    extra = {"user": {k: v for k, v in {
        "legal_name": params.legal_name, "phone_number": params.phone_number,
        "email_address": params.email_address, "address": params.address or None,
    }.items() if v}}
    data, err = await _item_call(ctx, params, "/identity/match", extra)
    if err:
        return err
    return ActionResult.success(data, "Identity match score retrieved.")


# ──────────────────────────────────────────────────────────────────────────
# Investments & Liabilities
# ──────────────────────────────────────────────────────────────────────────


@chat.function("get_holdings", "Read investment holdings (securities owned, quantity, cost basis) for an Item's investment accounts.", action_type="read")
async def get_holdings(ctx, params: GetHoldingsParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/investments/holdings/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Investment holdings retrieved.")


@chat.function("get_investment_transactions", "Read investment transactions (buys, sells, dividends, fees) for an Item within a date range.", action_type="read")
async def get_investment_transactions(ctx, params: GetInvestmentTransactionsParams) -> ActionResult:
    extra = {
        "start_date": params.start_date, "end_date": params.end_date,
        "options": {"count": params.count, "offset": params.offset},
    }
    if params.account_ids:
        extra["options"]["account_ids"] = params.account_ids
    data, err = await _item_call(ctx, params, "/investments/transactions/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Investment transactions retrieved.")


@chat.function("refresh_investments", "Ask Plaid to proactively check for new investment data right now instead of waiting for its normal refresh schedule.", action_type="write", effects=["plaid.investments.refresh_requested"], event="plaid-connector.refresh_investments")
async def refresh_investments(ctx, params: RefreshInvestmentsParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/investments/refresh")
    if err:
        return err
    return ActionResult.success({"requested": True}, "Investments refresh requested.")


@chat.function("get_liabilities", "Read liability details (student loans, credit cards, mortgages -- APR, balances, due dates) for an Item.", action_type="read")
async def get_liabilities(ctx, params: GetLiabilitiesParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/liabilities/get", extra)
    if err:
        return err
    return ActionResult.success(data, "Liabilities retrieved.")


# ──────────────────────────────────────────────────────────────────────────
# Assets (Asset Report -- multi-Item point-in-time snapshot for underwriting)
# ──────────────────────────────────────────────────────────────────────────


async def _env_call(ctx, connection_id: str, environment: str, path: str, body: dict) -> tuple[dict | None, ActionResult | None]:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, connection_id)
    if not conn:
        return None, _no_connection_error(connection_id, connections)
    secret = _secret_for(conn, environment)
    if not secret:
        return None, ActionResult.error(f"No {environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")
    try:
        data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                 environment=environment, path=path, body=body)
    except pc.ClientFail as e:
        return None, _err(e)
    return data, None


@chat.function("create_asset_report", "Create an Asset Report -- a point-in-time snapshot of balances/transactions across one or more Items, used for mortgage/loan underwriting.", action_type="write", effects=["plaid.asset_report.created"], event="plaid-connector.create_asset_report")
async def create_asset_report(ctx, params: CreateAssetReportParams) -> ActionResult:
    body = {"access_tokens": params.access_tokens, "days_requested": params.days_requested}
    options = {}
    if params.client_report_id:
        options["client_report_id"] = params.client_report_id
    if params.webhook:
        options["webhook"] = params.webhook
    if params.user:
        options["user"] = params.user
    if options:
        body["options"] = options
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/create", body)
    if err:
        return err
    return ActionResult.success(data, "Asset Report requested -- poll get_asset_report until PRODUCT_READY fires.")


@chat.function("get_asset_report", "Read a previously created Asset Report by its token, once Plaid's PRODUCT_READY webhook has fired.", action_type="read")
async def get_asset_report(ctx, params: GetAssetReportParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token, "include_insights": params.include_insights}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/get", body)
    if err:
        return err
    return ActionResult.success(data, "Asset Report retrieved.")


@chat.function("get_asset_report_pdf", "Render a completed Asset Report as a PDF, base64-encoded.", action_type="read")
async def get_asset_report_pdf(ctx, params: GetAssetReportPdfParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/pdf/get", body)
    if err:
        return err
    return ActionResult.success(data, "Asset Report PDF retrieved.")


@chat.function("refresh_asset_report", "Refresh an existing Asset Report with up-to-date balance/transaction data.", action_type="write", effects=["plaid.asset_report.refreshed"], event="plaid-connector.refresh_asset_report")
async def refresh_asset_report(ctx, params: RefreshAssetReportParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token, "days_requested": params.days_requested}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/refresh", body)
    if err:
        return err
    return ActionResult.success(data, "Asset Report refresh requested.")


@chat.function("filter_asset_report", "Create a new, filtered copy of an Asset Report with specific accounts excluded -- e.g. to hide accounts irrelevant to a loan application.", action_type="write", effects=["plaid.asset_report.filtered"], event="plaid-connector.filter_asset_report")
async def filter_asset_report(ctx, params: FilterAssetReportParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token, "account_ids_to_exclude": params.account_ids_to_exclude}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/filter", body)
    if err:
        return err
    return ActionResult.success(data, "Filtered Asset Report requested.")


@chat.function("remove_asset_report", "Permanently delete an Asset Report. Cannot be undone.", action_type="write", effects=["plaid.asset_report.removed"], event="plaid-connector.remove_asset_report")
async def remove_asset_report(ctx, params: RemoveAssetReportParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/remove", body)
    if err:
        return err
    return ActionResult.success({"removed": True}, "Asset Report removed.")


@chat.function("create_audit_copy", "Create an auditor-shareable copy of an Asset Report for a named auditing institution (e.g. Fannie Mae).", action_type="write", effects=["plaid.asset_report.audit_copy_created"], event="plaid-connector.create_audit_copy")
async def create_audit_copy(ctx, params: CreateAuditCopyParams) -> ActionResult:
    body = {"asset_report_token": params.asset_report_token, "auditor_id": params.auditor_id}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/audit_copy/create", body)
    if err:
        return err
    return ActionResult.success(data, "Audit copy created.")


@chat.function("remove_audit_copy", "Revoke a previously created Asset Report audit copy.", action_type="write", effects=["plaid.asset_report.audit_copy_removed"], event="plaid-connector.remove_audit_copy")
async def remove_audit_copy(ctx, params: RemoveAuditCopyParams) -> ActionResult:
    body = {"audit_copy_token": params.audit_copy_token}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/asset_report/audit_copy/remove", body)
    if err:
        return err
    return ActionResult.success({"removed": True}, "Audit copy revoked.")


# ──────────────────────────────────────────────────────────────────────────
# Income
# ──────────────────────────────────────────────────────────────────────────


@chat.function("create_income_verification", "Start Payroll/Document income verification for an Item.", action_type="write", effects=["plaid.income_verification.created"], event="plaid-connector.create_income_verification")
async def create_income_verification(ctx, params: CreateIncomeVerificationParams) -> ActionResult:
    body = {}
    if params.access_token:
        body["access_token"] = params.access_token
    if params.webhook:
        body["webhook"] = params.webhook
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/income/verification/create", body)
    if err:
        return err
    return ActionResult.success(data, "Income verification requested.")


@chat.function("get_income_verification", "Read a previously created Payroll/Document income verification's result by its id.", action_type="read")
async def get_income_verification(ctx, params: GetIncomeVerificationParams) -> ActionResult:
    body = {"income_verification_id": params.income_verification_id}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/income/verification/paystubs/get", body)
    if err:
        return err
    return ActionResult.success(data, "Income verification retrieved.")


@chat.function("get_bank_income", "Read a Bank Income estimate derived purely from an Item's own transaction history -- no separate payroll flow needed.", action_type="read")
async def get_bank_income(ctx, params: GetBankIncomeParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/credit/bank_income/get")
    if err:
        return err
    return ActionResult.success(data, "Bank Income estimate retrieved.")


# ──────────────────────────────────────────────────────────────────────────
# Transfer (ACH / RTP / same-day-ACH / wire money movement)
# ──────────────────────────────────────────────────────────────────────────


@chat.function("create_transfer_authorization", "Get a real-time risk authorization decision BEFORE creating a Transfer -- Plaid requires a fresh authorization_id for every real Transfer.", action_type="write", effects=["plaid.transfer_authorization.created"], event="plaid-connector.create_transfer_authorization")
async def create_transfer_authorization(ctx, params: CreateTransferAuthorizationParams) -> ActionResult:
    extra = {"account_id": params.account_id, "type": params.type, "network": params.network,
             "amount": params.amount, "ach_class": params.ach_class,
             "user": params.user}
    data, err = await _item_call(ctx, params, "/transfer/authorization/create", extra)
    if err:
        return err
    return ActionResult.success(data, "Transfer authorization decision retrieved.")


@chat.function("create_transfer", "Create a real Transfer (moves real money) using a prior authorization_id.", action_type="write", effects=["plaid.transfer.created"], event="plaid-connector.create_transfer")
async def create_transfer(ctx, params: CreateTransferParams) -> ActionResult:
    extra = {"authorization_id": params.authorization_id, "account_id": params.account_id,
             "description": params.description, "amount": params.amount}
    data, err = await _item_call(ctx, params, "/transfer/create", extra)
    if err:
        return err
    return ActionResult.success(data, "Transfer created.")


@chat.function("get_transfer", "Read one Transfer in full by its id -- status, amount, and network.", action_type="read")
async def get_transfer(ctx, params: GetTransferParams) -> ActionResult:
    body = {"transfer_id": params.transfer_id}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/transfer/get", body)
    if err:
        return err
    return ActionResult.success(data, "Transfer retrieved.")


@chat.function("list_transfers", "List Transfers on this Plaid account.", action_type="read")
async def list_transfers(ctx, params: ListTransfersParams) -> ActionResult:
    body = {"count": params.count, "offset": params.offset}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/transfer/list", body)
    if err:
        return err
    transfers = data.get("transfers", [])
    return ActionResult.success(transfers, f"{len(transfers)} transfer(s).")


@chat.function("cancel_transfer", "Cancel a Transfer while it is still pending.", action_type="write", effects=["plaid.transfer.canceled"], event="plaid-connector.cancel_transfer")
async def cancel_transfer(ctx, params: CancelTransferParams) -> ActionResult:
    body = {"transfer_id": params.transfer_id}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/transfer/cancel", body)
    if err:
        return err
    return ActionResult.success(data, "Transfer canceled.")


@chat.function("create_transfer_refund", "Refund a completed Transfer, fully or partially.", action_type="write", effects=["plaid.transfer.refunded"], event="plaid-connector.create_transfer_refund")
async def create_transfer_refund(ctx, params: CreateTransferRefundParams) -> ActionResult:
    body = {"transfer_id": params.transfer_id}
    if params.amount:
        body["amount"] = params.amount
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/transfer/refund/create", body)
    if err:
        return err
    return ActionResult.success(data, "Transfer refund created.")


@chat.function("list_transfer_events", "List Transfer lifecycle events (posted, settled, failed, returned, swept) -- your source of truth for reconciling Transfer status changes.", action_type="read")
async def list_transfer_events(ctx, params: ListTransferEventsParams) -> ActionResult:
    body = {"count": params.count, "offset": params.offset}
    if params.transfer_id:
        body["transfer_id"] = params.transfer_id
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/transfer/event/list", body)
    if err:
        return err
    events = data.get("transfer_events", [])
    return ActionResult.success(events, f"{len(events)} transfer event(s).")


# ──────────────────────────────────────────────────────────────────────────
# Signal (real-time ACH return-risk score) & Monitor/Watchlist Screening
# ──────────────────────────────────────────────────────────────────────────


@chat.function("evaluate_signal", "Get a real-time ACH return-risk score for a proposed debit BEFORE you initiate it, from Plaid Signal.", action_type="read")
async def evaluate_signal(ctx, params: EvaluateSignalParams) -> ActionResult:
    extra = {"account_id": params.account_id, "client_transaction_id": params.client_transaction_id,
             "amount": params.amount}
    if params.user:
        extra["user"] = params.user
    data, err = await _item_call(ctx, params, "/signal/evaluate", extra)
    if err:
        return err
    return ActionResult.success(data, "Signal risk score retrieved.")


@chat.function("report_signal_decision", "Report back to Plaid whether you actually initiated an ACH transaction after seeing its Signal score -- improves future score accuracy.", action_type="write", effects=["plaid.signal_decision.reported"], event="plaid-connector.report_signal_decision")
async def report_signal_decision(ctx, params: ReportSignalDecisionParams) -> ActionResult:
    body = {"client_transaction_id": params.client_transaction_id, "initiated": params.initiated}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/signal/decision/report", body)
    if err:
        return err
    return ActionResult.success(data, "Signal decision reported.")


@chat.function("create_watchlist_screening", "Screen a person against global watchlists (sanctions, PEP, adverse media) with Plaid Monitor.", action_type="write", effects=["plaid.watchlist_screening.created"], event="plaid-connector.create_watchlist_screening")
async def create_watchlist_screening(ctx, params: CreateWatchlistScreeningParams) -> ActionResult:
    body = {"search_terms": params.search_terms}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/watchlist_screening/individual/create", body)
    if err:
        return err
    return ActionResult.success(data, "Watchlist screening created.")


@chat.function("get_watchlist_screening", "Read one watchlist screening's result in full by its id -- match status and any hits found.", action_type="read")
async def get_watchlist_screening(ctx, params: GetWatchlistScreeningParams) -> ActionResult:
    body = {"id": params.screening_id}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/watchlist_screening/individual/get", body)
    if err:
        return err
    return ActionResult.success(data, "Watchlist screening retrieved.")


@chat.function("list_watchlist_screenings", "List watchlist screenings created on this connection, most recent first.", action_type="read")
async def list_watchlist_screenings(ctx, params: ListWatchlistScreeningsParams) -> ActionResult:
    body = {"count": params.count}
    if params.cursor:
        body["cursor"] = params.cursor
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/watchlist_screening/individual/list", body)
    if err:
        return err
    screenings = data.get("individual_watchlist_screenings", [])
    return ActionResult.success(screenings, f"{len(screenings)} watchlist screening(s).")


@chat.function("review_watchlist_screening", "Record a human review decision (confirmed match / dismissed as false positive) on a watchlist screening's hit.", action_type="write", effects=["plaid.watchlist_screening.reviewed"], event="plaid-connector.review_watchlist_screening")
async def review_watchlist_screening(ctx, params: ReviewWatchlistScreeningParams) -> ActionResult:
    body = {"screening_id": params.screening_id, "confirmed_hits": params.confirmed_hits,
            "dismissed_hits": params.dismissed_hits, "comment": params.comment}
    data, err = await _env_call(ctx, params.connection_id, params.environment, "/watchlist_screening/individual/review/create", body)
    if err:
        return err
    return ActionResult.success(data, "Watchlist screening review recorded.")


# ──────────────────────────────────────────────────────────────────────────
# Processor tokens (hand off an Item to a third-party payment processor)
# ──────────────────────────────────────────────────────────────────────────


@chat.function("create_processor_token", "Create a processor_token for an account, to hand it off to a supported payment processor (e.g. Dwolla, Stripe, Braintree) without exposing your Plaid access_token to them.", action_type="write", effects=["plaid.processor_token.created"], event="plaid-connector.create_processor_token")
async def create_processor_token(ctx, params: CreateProcessorTokenParams) -> ActionResult:
    extra = {"account_id": params.account_id, "processor": params.processor}
    data, err = await _item_call(ctx, params, "/processor/token/create", extra)
    if err:
        return err
    return ActionResult.success(data, "Processor token created.")


@chat.function("create_bank_account_token", "Create a bank_account_token for an account -- a newer, processor-agnostic alternative to create_processor_token for handing off an Item to a partner.", action_type="write", effects=["plaid.bank_account_token.created"], event="plaid-connector.create_bank_account_token")
async def create_bank_account_token(ctx, params: CreateBankAccountTokenParams) -> ActionResult:
    extra = {"account_id": params.account_id}
    data, err = await _item_call(ctx, params, "/processor/bank_account_token/create", extra)
    if err:
        return err
    return ActionResult.success(data, "Bank account token created.")


# ──────────────────────────────────────────────────────────────────────────
# Sandbox test helpers (only meaningful against environment='sandbox')
# ──────────────────────────────────────────────────────────────────────────


@chat.function("create_sandbox_public_token", "Create a fake public_token for a Sandbox test institution, so you can exercise exchange_public_token without going through real Plaid Link.", action_type="write", effects=["plaid.sandbox_public_token.created"], event="plaid-connector.create_sandbox_public_token")
async def create_sandbox_public_token(ctx, params: CreateSandboxPublicTokenParams) -> ActionResult:
    body = {"institution_id": params.institution_id, "initial_products": params.initial_products}
    data, err = await _env_call(ctx, params.connection_id, "sandbox", "/sandbox/public_token/create", body)
    if err:
        return err
    return ActionResult.success(data, "Sandbox public token created.")


@chat.function("fire_sandbox_webhook", "Force a Sandbox Item to fire a specific webhook right now, so you can test your webhook handler without waiting for real data changes.", action_type="write", effects=["plaid.sandbox_webhook.fired"], event="plaid-connector.fire_sandbox_webhook")
async def fire_sandbox_webhook(ctx, params: FireSandboxWebhookParams) -> ActionResult:
    extra = {"webhook_code": params.webhook_code, "webhook_type": params.webhook_type}
    data, err = await _item_call(ctx, params, "/sandbox/item/fire_webhook", extra)
    if err:
        return err
    return ActionResult.success(data, "Sandbox webhook fired.")


@chat.function("reset_sandbox_item_login", "Force a Sandbox Item into ITEM_LOGIN_REQUIRED, to test your reauthentication (update-mode Link) flow on demand.", action_type="write", effects=["plaid.sandbox_item.reset"], event="plaid-connector.reset_sandbox_item_login")
async def reset_sandbox_item_login(ctx, params: ResetSandboxItemLoginParams) -> ActionResult:
    data, err = await _item_call(ctx, params, "/sandbox/item/reset_login")
    if err:
        return err
    return ActionResult.success(data, "Sandbox Item login reset requested.")


@chat.function("set_sandbox_verification_status", "Set a Sandbox account's micro-deposit verification status, to test your Auth verification flow's different outcomes on demand.", action_type="write", effects=["plaid.sandbox_verification.set"], event="plaid-connector.set_sandbox_verification_status")
async def set_sandbox_verification_status(ctx, params: SetSandboxVerificationStatusParams) -> ActionResult:
    extra = {"account_id": params.account_id, "verification_status": params.verification_status}
    data, err = await _item_call(ctx, params, "/sandbox/item/set_verification_status", extra)
    if err:
        return err
    return ActionResult.success(data, "Sandbox verification status set.")


@chat.function("create_sandbox_transactions", "Inject fake transactions into a Sandbox Item, so downstream transactions/enrichment testing has realistic data to work with.", action_type="write", effects=["plaid.sandbox_transactions.created"], event="plaid-connector.create_sandbox_transactions")
async def create_sandbox_transactions(ctx, params: CreateSandboxTransactionsParams) -> ActionResult:
    extra = {"transactions": params.transactions}
    data, err = await _item_call(ctx, params, "/sandbox/transactions/create", extra)
    if err:
        return err
    return ActionResult.success(data, "Sandbox transactions injected.")


# ──────────────────────────────────────────────────────────────────────────
# Value-add reports (Tier 3 -- built by Imperal, not raw Plaid endpoints)
# ──────────────────────────────────────────────────────────────────────────


@chat.function("audit_item_health", "Build one aggregated health report across several Plaid Items: which ones need reauthentication (ITEM_LOGIN_REQUIRED), which have pending errors, and their institution names.", action_type="read")
async def audit_item_health(ctx, params: AuditItemHealthParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")

    rows = []
    healthy = 0
    for token in params.access_tokens:
        try:
            data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                     environment=params.environment, path="/item/get",
                                     body={"access_token": token})
        except pc.ClientFail as e:
            rows.append({"access_token_suffix": token[-6:], "status": "error", "detail": pc.message_for(e)})
            continue
        item = data.get("item", {})
        err = item.get("error")
        status = "needs_reauth" if err and err.get("error_code") == "ITEM_LOGIN_REQUIRED" else ("error" if err else "healthy")
        if status == "healthy":
            healthy += 1
        rows.append({
            "access_token_suffix": token[-6:], "item_id": item.get("item_id"),
            "institution_id": item.get("institution_id"), "status": status,
            "error_code": (err or {}).get("error_code"),
        })
    return ActionResult.success(
        {"items": rows, "healthy_count": healthy, "total_count": len(params.access_tokens)},
        f"{healthy}/{len(params.access_tokens)} Item(s) healthy.",
    )


@chat.function("get_spending_overview", "Summarize spending by category for an Item's transactions over a date range -- total spend, top categories, and transaction count.", action_type="read")
async def get_spending_overview(ctx, params: GetSpendingOverviewParams) -> ActionResult:
    extra = {
        "start_date": params.start_date, "end_date": params.end_date,
        "options": {"count": 500, "offset": 0},
    }
    if params.account_ids:
        extra["options"]["account_ids"] = params.account_ids
    data, err = await _item_call(ctx, params, "/transactions/get", extra)
    if err:
        return err
    txns = data.get("transactions", [])
    by_category: dict[str, float] = {}
    total = 0.0
    for t in txns:
        if t.get("amount", 0) <= 0:
            continue  # negative amounts are inflows/refunds in Plaid's sign convention
        cat = (t.get("personal_finance_category") or {}).get("primary") or (t.get("category") or ["Uncategorized"])[0]
        by_category[cat] = by_category.get(cat, 0.0) + t["amount"]
        total += t["amount"]
    top = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return ActionResult.success(
        {"total_spend": round(total, 2), "transaction_count": len(txns),
         "top_categories": [{"category": c, "amount": round(a, 2)} for c, a in top]},
        f"Total spend {round(total, 2)} across {len(txns)} transaction(s).",
    )


@chat.function("detect_recurring_charges", "Flag subscriptions/recurring charges the end user may have forgotten about, using Plaid's own recurring-transaction detection.", action_type="read")
async def detect_recurring_charges(ctx, params: DetectRecurringChargesParams) -> ActionResult:
    extra = {"account_ids": params.account_ids} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/transactions/recurring/get", extra)
    if err:
        return err
    outflows = data.get("outflow_streams", [])
    active = [s for s in outflows if s.get("is_active")]
    return ActionResult.success(
        {"recurring_charges": active, "active_count": len(active), "total_streams": len(outflows)},
        f"{len(active)} active recurring charge stream(s) detected.",
    )


@chat.function("get_net_worth_snapshot", "Combine balances across several Items (depository + investments + liabilities) into one net-worth snapshot: assets, liabilities, and the difference.", action_type="read")
async def get_net_worth_snapshot(ctx, params: GetNetWorthSnapshotParams) -> ActionResult:
    connections = await _get_connections(ctx)
    conn = await _resolve_connection(ctx, params.connection_id)
    if not conn:
        return _no_connection_error(params.connection_id, connections)
    secret = _secret_for(conn, params.environment)
    if not secret:
        return ActionResult.error(f"No {params.environment} secret saved on this connection.", code="ENV_NOT_CONFIGURED")

    assets_total = 0.0
    liabilities_total = 0.0
    per_item = []
    for token in params.access_tokens:
        try:
            data = await pc.request(ctx=ctx, client_id=conn["client_id"], secret=secret,
                                     environment=params.environment, path="/accounts/get",
                                     body={"access_token": token})
        except pc.ClientFail as e:
            per_item.append({"access_token_suffix": token[-6:], "error": pc.message_for(e)})
            continue
        item_assets = 0.0
        item_liabilities = 0.0
        for a in data.get("accounts", []):
            bal = (a.get("balances") or {}).get("current") or 0.0
            if a.get("type") in ("credit", "loan"):
                item_liabilities += bal
            else:
                item_assets += bal
        assets_total += item_assets
        liabilities_total += item_liabilities
        per_item.append({"access_token_suffix": token[-6:], "assets": round(item_assets, 2), "liabilities": round(item_liabilities, 2)})
    return ActionResult.success(
        {"total_assets": round(assets_total, 2), "total_liabilities": round(liabilities_total, 2),
         "net_worth": round(assets_total - liabilities_total, 2), "per_item": per_item},
        f"Net worth: {round(assets_total - liabilities_total, 2)}.",
    )


@chat.function("check_low_balance_risk", "Flag accounts on an Item whose current balance is at or below a threshold -- a quick way to catch overdraft risk before it happens.", action_type="read")
async def check_low_balance_risk(ctx, params: CheckLowBalanceRiskParams) -> ActionResult:
    extra = {"options": {"account_ids": params.account_ids}} if params.account_ids else None
    data, err = await _item_call(ctx, params, "/accounts/get", extra)
    if err:
        return err
    at_risk = []
    for a in data.get("accounts", []):
        bal = (a.get("balances") or {}).get("current")
        if bal is not None and bal <= params.threshold:
            at_risk.append({"account_id": a.get("account_id"), "name": a.get("name"), "current_balance": bal})
    return ActionResult.success(
        {"at_risk_accounts": at_risk, "threshold": params.threshold},
        f"{len(at_risk)} account(s) at or below {params.threshold}.",
    )


@chat.function("list_available_products", "List every Plaid product this connector supports, with a one-line description of what each does -- a quick reference before calling create_link_token.", action_type="read")
async def list_available_products(ctx, params: ListAvailableProductsParams) -> ActionResult:
    products = [
        {"product": "transactions", "description": "Categorized transaction history via sync_transactions/get_transactions."},
        {"product": "auth", "description": "Account and routing numbers for ACH origination."},
        {"product": "identity", "description": "Account holder name/email/phone/address on file at the bank."},
        {"product": "investments", "description": "Holdings and investment transactions."},
        {"product": "liabilities", "description": "Credit card, student loan, and mortgage balances/terms."},
        {"product": "assets", "description": "Point-in-time Asset Report snapshots for underwriting."},
        {"product": "income_verification", "description": "Payroll/Document income verification, plus Bank Income estimates."},
        {"product": "transfer", "description": "ACH/RTP/same-day-ACH/wire money movement."},
        {"product": "signal", "description": "Real-time ACH return-risk scoring."},
        {"product": "monitor", "description": "Ongoing watchlist/sanctions screening (Plaid Monitor)."},
        {"product": "identity_verification", "description": "Document + selfie identity verification (not yet wrapped -- open a request if needed)."},
    ]
    return ActionResult.success(products, f"{len(products)} Plaid product(s) documented.")

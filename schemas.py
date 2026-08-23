"""Pydantic params models + SDL entity contracts for Plaid Connector.

WHY MOSTLY GENERIC `PlaidObject`/dict-shaped ENTITIES, NOT ONE HAND-TYPED
CLASS PER PLAID OBJECT (same reasoning as Stripe Connector's schemas.py).

Plaid exposes dozens of object shapes across Items/Accounts/Transactions/
Investments/Liabilities/Identity/Assets/Income/Transfer/Signal/Monitor.
Hand-typing every one would mean 40+ near-duplicate classes that just
mirror Plaid's own JSON shape back. High-traffic objects (Item, Account,
Institution, Transaction) get real typed Entities so they render well in
chat/panels; everything else is returned as plain dicts wrapped by a
generic `PlaidObject` Entity, still SDL-valid (has id/title/kind).

WHY `environment: str = "sandbox"` ON NEARLY EVERY PARAMS MODEL.

Every Plaid call must state which of the two live environments
(sandbox/production) it targets, because client_id is shared but secret
is per-environment (see plaid_client.py). Defaulting to "sandbox" is the
safe choice -- a stray/careless call never accidentally touches
production/real bank data.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectPlaidParams(BaseModel):
    client_id: str = Field(
        "",
        description="Your Plaid client_id, shared across Sandbox and "
        "Production. Found in Plaid Dashboard > Team Settings > Keys.",
    )
    sandbox_secret: str = Field(
        "",
        description="Your Plaid Sandbox secret (only needed if you want "
        "to test with fake bank data). Leave blank if you only use "
        "Production.",
    )
    production_secret: str = Field(
        "",
        description="Your Plaid Production secret (real bank data, "
        "billed by Plaid). Leave blank if you only use Sandbox.",
    )
    label: str = Field(
        "",
        description="A short name for this Plaid connection, e.g. "
        "'Main fintech app' -- helps you tell connections apart if you "
        "connect more than one Plaid account.",
    )


class ConnectionIdParam(BaseModel):
    connection_id: str = Field(
        "", description="Which saved Plaid connection to use. Leave "
        "blank to use the only one connected (fails if there is more "
        "than one)."
    )


class DisconnectPlaidParams(ConnectionIdParam):
    pass


class ListConnectionsParams(NoParams):
    pass


# ──────────────────────────────────────────────────────────────────────────
# Link (frontend token issuance -- the connector never renders Link itself)
# ──────────────────────────────────────────────────────────────────────────


class CreateLinkTokenParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to create the Link token in: 'sandbox' or 'production'.")
    client_user_id: str = Field(..., description="Your own stable identifier for the end user who will go through Plaid Link, e.g. their internal user id in your app.")
    client_name: str = Field(..., description="The name of your app, shown to the end user inside Plaid Link, e.g. 'Acme Budgeting App'.")
    products: list[str] = Field(default_factory=lambda: ["transactions"], description="Plaid products to request access to, e.g. ['transactions','auth','identity']. See list_available_products for the full catalog.")
    country_codes: list[str] = Field(default_factory=lambda: ["US"], description="ISO country codes Link should support, e.g. ['US','CA','GB'].")
    language: str = Field("en", description="Language code shown in Link, e.g. 'en', 'es', 'fr'.")
    redirect_uri: str = Field("", description="OAuth redirect URI registered in your Plaid Dashboard, required only for OAuth institutions.")
    webhook: str = Field("", description="HTTPS URL Plaid should send Item webhooks to once the user finishes linking.")
    access_token: str = Field("", description="An existing Item's access_token, to create an update-mode Link token (e.g. to fix ITEM_LOGIN_REQUIRED) instead of a new-Item token.")


class GetLinkTokenParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Link token was created in.")
    link_token: str = Field(..., description="The link_token returned by create_link_token, to check its current status and metadata.")


class ExchangePublicTokenParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the public_token was issued in.")
    public_token: str = Field(..., description="The public_token Plaid Link returned to your frontend after the end user finished linking their bank -- exchanged here for a durable access_token.")


# ──────────────────────────────────────────────────────────────────────────
# Items (the durable link between one end user's bank login and your app)
# ──────────────────────────────────────────────────────────────────────────


class ItemActionParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment this Item lives in.")
    access_token: str = Field(..., description="The access_token for the Item to act on (from exchange_public_token).")


class RemoveItemParams(ItemActionParams):
    pass


class GetItemParams(ItemActionParams):
    pass


class UpdateItemWebhookParams(ItemActionParams):
    webhook: str = Field(..., description="The new HTTPS URL Plaid should send this Item's webhooks to.")


class CreatePublicTokenParams(ItemActionParams):
    """Re-issue a short-lived public_token for an existing Item -- used to
    launch Link in update mode from a different client than the one that
    originally created the Item."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Accounts & Institutions
# ──────────────────────────────────────────────────────────────────────────


class GetAccountsParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit results to these specific account ids. Leave empty to return every account on this Item.")


class GetInstitutionParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to look up the institution in.")
    institution_id: str = Field(..., description="The Plaid institution id, e.g. 'ins_109508'.")
    country_codes: list[str] = Field(default_factory=lambda: ["US"], description="ISO country codes to scope the lookup to.")


class ListInstitutionsParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to list institutions in.")
    count: int = Field(50, description="How many institutions to return, max 500.")
    offset: int = Field(0, description="Pagination offset.")
    country_codes: list[str] = Field(default_factory=lambda: ["US"], description="ISO country codes to scope the list to.")


class SearchInstitutionsParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to search institutions in.")
    query: str = Field(..., description="Free-text institution name to search for, e.g. 'Chase'.")
    products: list[str] = Field(default_factory=lambda: ["transactions"], description="Only return institutions that support these products.")
    country_codes: list[str] = Field(default_factory=lambda: ["US"], description="ISO country codes to scope the search to.")


# ──────────────────────────────────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────────────────────────────────


class SyncTransactionsParams(ItemActionParams):
    cursor: str = Field("", description="Cursor from a previous sync_transactions call to fetch only new changes. Leave blank on the very first sync for this Item.")
    count: int = Field(100, description="Max number of updates to return in this page, up to 500.")


class GetTransactionsParams(ItemActionParams):
    start_date: str = Field(..., description="Start of the date range, YYYY-MM-DD.")
    end_date: str = Field(..., description="End of the date range, YYYY-MM-DD.")
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")
    count: int = Field(100, description="Max transactions to return, up to 500.")
    offset: int = Field(0, description="Pagination offset.")


class RefreshTransactionsParams(ItemActionParams):
    pass


class GetRecurringTransactionsParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class EnrichTransactionsParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to call Transactions Enrich in.")
    account_type: str = Field("depository", description="Account type the raw transactions came from, e.g. 'depository' or 'credit'.")
    transactions: list[dict] = Field(..., description="Raw transaction objects (not from Plaid) to enrich with merchant/category/logo data -- each needs at minimum id, description, amount, iso_currency_code, date, direction.")


# ──────────────────────────────────────────────────────────────────────────
# Auth (routing/account numbers) & Identity
# ──────────────────────────────────────────────────────────────────────────


class GetAuthParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class GetIdentityParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class MatchIdentityParams(ItemActionParams):
    legal_name: str = Field("", description="The name to match against the account holder's name on file.")
    phone_number: str = Field("", description="The phone number to match, E.164 format e.g. +14151234567.")
    email_address: str = Field("", description="The email address to match.")
    address: dict = Field(default_factory=dict, description="Address object to match, e.g. {'street':..,'city':..,'region':..,'postal_code':..,'country':..}.")


# ──────────────────────────────────────────────────────────────────────────
# Investments & Liabilities
# ──────────────────────────────────────────────────────────────────────────


class GetHoldingsParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these investment account ids.")


class GetInvestmentTransactionsParams(ItemActionParams):
    start_date: str = Field(..., description="Start of the date range, YYYY-MM-DD.")
    end_date: str = Field(..., description="End of the date range, YYYY-MM-DD.")
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these investment account ids.")
    count: int = Field(100, description="Max transactions to return, up to 500.")
    offset: int = Field(0, description="Pagination offset.")


class RefreshInvestmentsParams(ItemActionParams):
    pass


class GetLiabilitiesParams(ItemActionParams):
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids (credit cards, student loans, mortgages).")


# ──────────────────────────────────────────────────────────────────────────
# Assets (Asset Report -- point-in-time PDF/JSON snapshot for underwriting)
# ──────────────────────────────────────────────────────────────────────────


class CreateAssetReportParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to create the Asset Report in.")
    access_tokens: list[str] = Field(..., description="One or more Item access_tokens to include in this single combined Asset Report.")
    days_requested: int = Field(60, description="How many days of transaction history to include, typically 60-730.")
    client_report_id: str = Field("", description="Your own id for this report, shown back to you later.")
    webhook: str = Field("", description="HTTPS URL Plaid should notify once the report is ready.")
    user: dict = Field(default_factory=dict, description="Optional borrower info to embed in the report, e.g. {'client_user_id':..,'first_name':..,'last_name':..,'ssn':..,'phone_number':..,'email':..}.")


class GetAssetReportParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token returned by create_asset_report.")
    include_insights: bool = Field(False, description="Whether to include Plaid's own cash-flow insights in the report.")


class GetAssetReportPdfParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token to render as a PDF.")


class RefreshAssetReportParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token to refresh with up-to-date data.")
    days_requested: int = Field(60, description="How many days of transaction history the refreshed report should cover.")


class FilterAssetReportParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token to filter.")
    account_ids_to_exclude: list[str] = Field(..., description="Account ids to remove from a new, filtered copy of the report.")


class RemoveAssetReportParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token to permanently delete.")


class CreateAuditCopyParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Asset Report was created in.")
    asset_report_token: str = Field(..., description="The asset_report_token to create an auditor-shareable copy of.")
    auditor_id: str = Field(..., description="The auditor id provided to you by the auditing institution (e.g. Fannie Mae).")


class RemoveAuditCopyParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the audit copy was created in.")
    audit_copy_token: str = Field(..., description="The audit_copy_token to revoke.")


# ──────────────────────────────────────────────────────────────────────────
# Income
# ──────────────────────────────────────────────────────────────────────────


class CreateIncomeVerificationParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to create the income verification in.")
    access_token: str = Field(..., description="The Item access_token to verify income for (Payroll/Document income) or leave blank for a Link-token-only Bank Income flow.")
    webhook: str = Field("", description="HTTPS URL Plaid should notify once verification completes.")


class GetIncomeVerificationParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the income verification was created in.")
    income_verification_id: str = Field(..., description="The income verification id to read.")


class GetBankIncomeParams(ItemActionParams):
    """Bank Income -- an income estimate derived purely from an already
    connected Item's own transaction history, no separate payroll flow."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Transfer (ACH / RTP / FedNow money movement)
# ──────────────────────────────────────────────────────────────────────────


class CreateTransferAuthorizationParams(ItemActionParams):
    account_id: str = Field(..., description="The Plaid account id to move money from/to.")
    type: str = Field("debit", description="'debit' (pull money from the account) or 'credit' (push money to the account).")
    network: str = Field("ach", description="Rail to use: 'ach', 'same-day-ach', 'rtp', or 'wire'.")
    amount: str = Field(..., description="Dollar amount as a decimal string, e.g. '12.34'.")
    ach_class: str = Field("web", description="ACH SEC code, e.g. 'web', 'ppd', 'ccd'.")
    user: dict = Field(..., description="End-user info required by network rules, e.g. {'legal_name':..,'phone_number':..,'email_address':..}.")


class CreateTransferParams(ItemActionParams):
    authorization_id: str = Field(..., description="The authorization_id from create_transfer_authorization -- Plaid requires a fresh authorization before every real Transfer.")
    account_id: str = Field(..., description="The Plaid account id to move money from/to.")
    description: str = Field(..., description="Up to 15 characters shown on the end user's bank statement.")
    amount: str = Field(..., description="Dollar amount as a decimal string, matching the authorization.")


class GetTransferParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the transfer was created in.")
    transfer_id: str = Field(..., description="The transfer id to read.")


class ListTransfersParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to list transfers in.")
    count: int = Field(25, description="Max transfers to return, up to 100.")
    offset: int = Field(0, description="Pagination offset.")


class CancelTransferParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the transfer was created in.")
    transfer_id: str = Field(..., description="The transfer id to cancel, only possible while still pending.")


class CreateTransferRefundParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the transfer was created in.")
    transfer_id: str = Field(..., description="The original transfer id to refund.")
    amount: str = Field("", description="Amount to refund as a decimal string. Leave blank to refund the full original amount.")


class ListTransferEventsParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to list transfer events in.")
    transfer_id: str = Field("", description="Optional: limit to events for one transfer id.")
    count: int = Field(25, description="Max events to return, up to 500.")
    offset: int = Field(0, description="Pagination offset.")


# ──────────────────────────────────────────────────────────────────────────
# Signal (real-time ACH return-risk score) & Monitor/Watchlist Screening
# ──────────────────────────────────────────────────────────────────────────


class EvaluateSignalParams(ItemActionParams):
    account_id: str = Field(..., description="The Plaid account id the proposed ACH debit would pull from.")
    client_transaction_id: str = Field(..., description="Your own unique id for this proposed transaction.")
    amount: float = Field(..., description="Proposed debit amount in dollars.")
    user: dict = Field(default_factory=dict, description="Optional end-user info to improve the risk score, e.g. {'name':..,'phone_number':..,'email_address':..}.")


class ReportSignalDecisionParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Signal evaluation was made in.")
    client_transaction_id: str = Field(..., description="The client_transaction_id from evaluate_signal to report the final outcome for.")
    initiated: bool = Field(..., description="Whether you actually initiated this ACH transaction after seeing the Signal score.")


class CreateWatchlistScreeningParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to create the screening in.")
    search_terms: dict = Field(..., description="Person to screen, e.g. {'legal_name':'Jane Doe','date_of_birth':'1990-01-01'}.")


class GetWatchlistScreeningParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the screening was created in.")
    screening_id: str = Field(..., description="The watchlist screening id to read.")


class ListWatchlistScreeningsParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to list screenings in.")
    count: int = Field(25, description="Max screenings to return, up to 500.")
    cursor: str = Field("", description="Pagination cursor from a previous call.")


class ReviewWatchlistScreeningParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the screening was created in.")
    screening_id: str = Field(..., description="The watchlist screening id to add a human review decision to.")
    confirmed_hits: list[str] = Field(default_factory=list, description="Watchlist hit ids confirmed as true matches.")
    dismissed_hits: list[str] = Field(default_factory=list, description="Watchlist hit ids dismissed as false positives.")
    comment: str = Field("", description="Free-text note explaining the review decision.")


# ──────────────────────────────────────────────────────────────────────────
# Processor tokens (hand off an Item to a payments partner, e.g. Stripe/Dwolla)
# ──────────────────────────────────────────────────────────────────────────


class CreateProcessorTokenParams(ItemActionParams):
    account_id: str = Field(..., description="The Plaid account id to create a processor token for.")
    processor: str = Field(..., description="The partner processor name, e.g. 'stripe', 'dwolla', 'circle', 'checkbook'.")


class CreateBankAccountTokenParams(ItemActionParams):
    """Universal processor-token equivalent used by newer partner
    integrations (Plaid's own recommended replacement token type)."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Sandbox-only helpers (no-ops in production, used for testing)
# ──────────────────────────────────────────────────────────────────────────


class CreateSandboxPublicTokenParams(ConnectionIdParam):
    institution_id: str = Field("ins_109508", description="The fake Sandbox institution id to simulate a login to, e.g. 'ins_109508' (a generic test bank).")
    initial_products: list[str] = Field(default_factory=lambda: ["transactions"], description="Products to enable on the fake Item, e.g. ['transactions','auth'].")
    webhook: str = Field("", description="Optional HTTPS URL to fire test webhooks to.")
    override_username: str = Field("user_good", description="Sandbox test username, e.g. 'user_good' or 'user_custom' for custom scenarios.")
    override_password: str = Field("pass_good", description="Sandbox test password matching the chosen username scenario.")


class FireSandboxWebhookParams(ItemActionParams):
    webhook_code: str = Field(..., description="Which webhook to simulate firing, e.g. 'DEFAULT_UPDATE', 'SYNC_UPDATES_AVAILABLE'.")
    webhook_type: str = Field("TRANSACTIONS", description="Which webhook family to fire it under, e.g. 'TRANSACTIONS', 'ITEM', 'AUTH', 'INVESTMENTS_TRANSACTIONS', 'HOLDINGS'.")


class ResetSandboxItemLoginParams(ItemActionParams):
    """Force a Sandbox Item into ITEM_LOGIN_REQUIRED, to test your
    reauthentication flow without waiting for a real credential change."""
    pass


class SetSandboxVerificationStatusParams(ItemActionParams):
    account_id: str = Field(..., description="The Sandbox account id to set a micro-deposit verification status on.")
    verification_status: str = Field(..., description="New status, e.g. 'automatically_verified', 'verification_expired', 'pending_manual_verification'.")


class CreateSandboxTransactionsParams(ItemActionParams):
    """Inject fake transactions into a Sandbox Item so downstream
    transactions/enrichment testing has realistic-looking data to chew on."""
    transactions: list[dict] = Field(..., description="Fake transaction objects to inject, e.g. [{'date_transacted':'2026-01-01','date_posted':'2026-01-02','amount':12.34,'description':'Coffee shop'}].")


# ──────────────────────────────────────────────────────────────────────────
# Value-add reports (Tier 3 -- built by Imperal, not raw Plaid endpoints)
# ──────────────────────────────────────────────────────────────────────────


class AuditItemHealthParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment to audit Items in.")
    access_tokens: list[str] = Field(..., description="The Item access_tokens to include in this health audit.")


class GetSpendingOverviewParams(ItemActionParams):
    start_date: str = Field(..., description="Start of the date range, YYYY-MM-DD.")
    end_date: str = Field(..., description="End of the date range, YYYY-MM-DD.")
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class DetectRecurringChargesParams(ItemActionParams):
    """Convenience wrapper flagging subscriptions/recurring charges the
    end user may have forgotten about, built on get_recurring_transactions
    plus a same-amount/same-merchant heuristic pass on raw transactions."""
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class GetNetWorthSnapshotParams(ConnectionIdParam):
    environment: str = Field("sandbox", description="Which Plaid environment the Items live in.")
    access_tokens: list[str] = Field(..., description="Item access_tokens to combine (depository + investments + liabilities) into one net-worth snapshot.")


class CheckLowBalanceRiskParams(ItemActionParams):
    threshold: float = Field(100.0, description="Balance threshold in dollars -- accounts at or below this are flagged as at-risk.")
    account_ids: list[str] = Field(default_factory=list, description="Optional: limit to these account ids.")


class ListAvailableProductsParams(NoParams):
    pass


# ──────────────────────────────────────────────────────────────────────────
# SDL Entity contracts
# ──────────────────────────────────────────────────────────────────────────


class PlaidConnectionEntity(sdl.Entity):
    """One saved Plaid client_id + per-environment secret pair."""
    kind: str = "plaid_connection"
    id: str
    title: str
    label: str = ""
    has_sandbox: bool = False
    has_production: bool = False


class PlaidItemEntity(sdl.Entity):
    """A Plaid Item -- the durable link between one end user's bank login
    and this connection, identified by its access_token's item_id."""
    kind: str = "plaid_item"
    id: str
    title: str
    institution_id: str = ""
    institution_name: str = ""
    environment: str = "sandbox"
    available_products: list[str] = Field(default_factory=list)
    billed_products: list[str] = Field(default_factory=list)


class PlaidAccountEntity(sdl.Entity):
    """One bank account (checking/savings/credit/loan/investment) under an Item."""
    kind: str = "plaid_account"
    id: str
    title: str
    official_name: str = ""
    type: str = ""
    subtype: str = ""
    mask: str = ""
    current_balance: float | None = None
    available_balance: float | None = None
    iso_currency_code: str = ""


class PlaidInstitutionEntity(sdl.Entity):
    """A bank/financial institution known to Plaid."""
    kind: str = "plaid_institution"
    id: str
    title: str
    country_codes: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    oauth: bool = False


class PlaidTransactionEntity(sdl.Entity):
    """One posted or pending transaction on an account."""
    kind: str = "plaid_transaction"
    id: str
    title: str
    account_id: str = ""
    amount: float = 0.0
    iso_currency_code: str = ""
    date: str = ""
    pending: bool = False
    category: list[str] = Field(default_factory=list)
    merchant_name: str = ""


class PlaidObject(sdl.Entity):
    """Generic wrapper for any Plaid response object that doesn't have a
    dedicated typed Entity above -- still SDL-valid (id/title/kind), raw
    payload preserved verbatim in `raw` for full-fidelity display."""
    kind: str = "plaid_object"
    id: str
    title: str
    raw: dict = Field(default_factory=dict)


class PlaidListEntity(sdl.Entity):
    """Generic wrapper for a list-shaped Plaid response (accounts, items,
    transactions, holdings, etc.) when returning many PlaidObject rows."""
    kind: str = "plaid_list"
    id: str
    title: str
    items: list[dict] = Field(default_factory=list)
    total_count: int = 0


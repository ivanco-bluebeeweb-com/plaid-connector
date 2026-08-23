# Pricing history — Plaid Connector

## 2026-08-23 — Initial per-action pricing map

- **Policy source:** `../../PRICING_POLICY.md`; only the canonical token values `{0, 8, 16, 20, 40, 60}` are used.
- **Coverage:** all 63 registered tools are explicitly priced in `tool-prices.json` and mirrored in `imperal.json["pricing"]`.
- **0 tokens:** `connect_plaid`, `disconnect_plaid`, and local `list_connections`. Connection setup/removal must not be paywalled; the connection list reads only Imperal’s saved connection inventory.
- **8 tokens:** external Plaid reads (`get_*`, `list_*`, institution search, transaction sync/enrichment) because each performs external service work.
- **16 tokens:** normal single-object writes such as Link/public/processor token creation, webhook and sandbox configuration, report removal, and decision/review reporting.
- **20 tokens:** consequential financial / underwriting / risk operations: Transfer authorization, creating/canceling/refunding a real transfer, Asset Report lifecycle writes, Income Verification, Signal evaluation, and watchlist-screening creation.
- **40 tokens:** Imperal-built multi-object financial diagnostics/reports: Item health audit, spending overview, recurring-charge analysis, net-worth snapshot, and low-balance-risk report.
- **60 tokens:** `create_sandbox_transactions`, which injects multiple transaction records in a single call.

### Platform persistence incident

`developer.update_pricing` was called with `pricing_model="per_action"`, the complete nested pricing map, and explicit `revenue_split_dev=95`. The platform verified that nothing persisted: it still stored `free` and no tool prices. This is a platform-side pricing persistence mismatch, not a successful pricing application. The manifest-backed map will be deployed first, then the primary update method will be retried; the issue is recorded in BBW Imperal Apps task #2317.

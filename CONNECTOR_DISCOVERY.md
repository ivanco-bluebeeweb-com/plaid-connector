# Plaid Connector — Connector Discovery

**Дата discovery:** 2026-08-22
**Статус:** Ярусы 1-3 пройдены (свежее чтение официальной документации plaid.com/docs, 2026-08-22). Влад заявил объём заранее — «максимальная форма со всеми доступными функциями с их стороны и всеми возможными функциями внутри нашего приложения для повышения эффективности» — поэтому по `CONNECTOR_DISCOVERY_STANDARD.md` Шаг 5 (запрос подтверждения объёма) считается закрытым этим прямым поручением: делаем Ярус 1+2+3.

---

## 1. Целевой сервис и источники

Plaid — крупнейший финтех-агрегатор Open Banking API в США/Канаде/Европе: связывает банковские счета конечных пользователей с приложениями через `Link` (frontend SDK) + серверный REST API. Это САМЫЙ широкий сервис из всех коннекторов в портфеле Imperal на сегодня — 15+ отдельных "продуктов", каждый со своей группой эндпоинтов и вебхуков, плюс отдельная Sandbox-поверхность для тестирования без реальных банков.

**Источники (прочитаны свежо, 2026-08-22):**
- plaid.com/docs/api/ (обзор, аутентификация, хосты)
- plaid.com/docs/api/link/ (Link tokens, `/link/token/create`, `/link/token/get`)
- plaid.com/docs/api/items/ (Items — `access_token` жизненный цикл)
- plaid.com/docs/api/accounts/ (`/accounts/get`, account type schema)
- plaid.com/docs/api/institutions/ (`/institutions/get`, `/get_by_id`, `/search`)
- plaid.com/docs/api/products/transactions/ + plaid.com/docs/transactions/webhooks/ (`/transactions/sync` — рекомендуемый endpoint, `/transactions/get` legacy)
- plaid.com/docs/api/products/auth/ (`/auth/get`, `/auth/verify`, micro-deposits)
- plaid.com/docs/api/products/identity/ (`/identity/get`, `/identity/match`)
- plaid.com/docs/api/products/investments/ (`/investments/holdings/get`, `/investments/transactions/get`, `/investments/refresh`)
- plaid.com/docs/api/products/liabilities/ (`/liabilities/get`)
- plaid.com/docs/api/products/assets/ (Asset Report — `/asset_report/create|get|pdf/get|refresh|filter|remove`, Credit Relay)
- plaid.com/docs/api/products/income/ (Income Verification — Payroll/Bank Income, `/user/create`)
- plaid.com/docs/api/products/transfer/ (ACH/RTP/FedNow money movement — самый большой отдельный подсервис: Initiating/Reading/Recurring/Refunds/Guaranteed ACH/Platforms/Ledger/Metrics)
- plaid.com/docs/api/products/signal/ (ACH-риск-скоринг, `/signal/evaluate`) + Balance (`/accounts/balance/get`)
- plaid.com/docs/api/products/monitor/ (Watchlist Screening — individual + entity, AML/sanctions)
- plaid.com/docs/api/products/beacon/ (DEPRECATED — фрод-сеть, все эндпоинты помечены Deprecated в официальных доках)
- plaid.com/docs/api/processors/ (`/processor/token/create` — для передачи доступа партнёрам типа Stripe/Dwolla)
- plaid.com/docs/api/sandbox/ (полный набор тестовых эндпоинтов — `/sandbox/public_token/create`, `/sandbox/item/*`, `/sandbox/transfer/*`, `/sandbox/income/fire_webhook`, `/sandbox/transactions/create`)
- plaid.com/docs/api/webhooks/webhook-verification/ (JWT-подписанные вебхуки, `/webhook_verification_key/get`)

**Не прочитано полностью (не критично для scope этого захода, страницы либо 404 на текущей структуре доков, либо out-of-scope по явному решению ниже):** `/products/employment/`, `/products/cra-base-report/` (Plaid Check / CRA-серия — консьюмер-репортинг для кредитных бюро, отдельный сильно регулируемый продукт США, требует отдельного одобрения Plaid и юридического режима FCRA — **сознательно исключаем из этого захода**, см. §7 ниже).

---

## 2. Классификация возможностей (Ingress / Egress / Both)

| Возможность Plaid | Направление | Комментарий |
|---|---|---|
| Link token create/get | Both | Создаёт токен инициализации frontend-флоу; get читает результат сессии |
| Item lifecycle (get/remove/webhook update/exchange/invalidate) | Both | Управление подключением банка |
| Accounts (`/accounts/get`, `/accounts/balance/get`) | Ingress | Чтение счетов и балансов |
| Institutions (`get`/`get_by_id`/`search`) | Ingress | Публичный справочник банков, не требует access_token |
| Transactions (`/transactions/sync`, `/transactions/get`, `/transactions/refresh`) | Ingress | Основной поток транзакций |
| Auth (`/auth/get`, `/auth/verify`) | Ingress | Номер счёта/роутинг для ACH |
| Identity (`/identity/get`, `/identity/match`) | Ingress | ФИО/email/телефон/адрес держателя счёта из банка |
| Investments (holdings/transactions/refresh) | Ingress | Портфель инвестиций |
| Liabilities (`/liabilities/get`) | Ingress | Кредиты/студенческие займы/ипотека |
| Assets / Asset Report (create/get/pdf/refresh/filter/remove, Credit Relay) | Both | Генерация отчёта — Egress-подобное действие (создание артефакта), потребление — Ingress |
| Income Verification (`/user/create`, bank/payroll income get, employment get) | Both | user/create — Egress (регистрация нового Plaid-пользователя), остальное — Ingress |
| Transfer (authorization/create, create, cancel, get/list, recurring, refund, ledger, platform onboarding) | Egress (money movement) | Реальные деньги — Tier с максимальным risk-gating |
| Signal (`/signal/evaluate`, decision/return report, prepare) | Both | Оценка риска ACH-транзакции перед инициацией |
| Monitor / Watchlist Screening (individual+entity CRUD, review, history, hit/program list) | Both | AML/санкционный скрининг сущностей |
| Beacon (все эндпоинты) | Both | DEPRECATED по официальным доках — не включаем в активную реализацию, см §7 |
| Processor tokens | Egress | Передача доступа третьей платёжной платформе (Stripe и др.) |
| Sandbox (`/sandbox/*`) | Both | Тестовые утилиты — критичны для Discovery/QA этого коннектора, не для конечного пользователя в проде, но нужны как встроенный dev/test инструментарий |
| Webhook verification (`/webhook_verification_key/get`) | Ingress | Проверка подлинности входящих вебхуков |

---

## 3. Ярус 1 — ключевые функции (must-have, P0)

Ядро "подключил банк → вижу счета/балансы/транзакции", без чего Plaid-коннектор бессмысленен:

1. `connect_plaid` — сохранить `client_id`/`secret`/`environment` (sandbox/production), проверить работоспособность вызовом `/institutions/get` с limit=1.
2. `disconnect_plaid` / `list_connections`.
3. `create_link_token` — обёртка `/link/token/create` (products, country_codes, language, user).
4. `exchange_public_token` — обёртка `/item/public_token/exchange` → сохраняет `access_token`+`item_id` за `connection_id`.
5. `get_item` / `remove_item` — статус Item, отключение банка.
6. `list_accounts` / `get_balances` — `/accounts/get`, `/accounts/balance/get`.
7. `sync_transactions` — `/transactions/sync` (рекомендуемый Plaid способ, курсор-based).
8. `list_institutions` / `search_institutions` / `get_institution` — публичный справочник, не требует access_token.
9. `refresh_transactions` — `/transactions/refresh` (форс-обновление на кнопку).

## 4. Ярус 2 — полное покрытие возможностей сервиса

Всё, что делает коннектор конкурентоспособным «максимальным» покрытием Plaid API:

**Auth (верификация счёта для ACH):** `get_auth`, `verify_auth` (Database Auth).
**Identity:** `get_identity`, `match_identity`.
**Investments:** `get_investment_holdings`, `get_investment_transactions`, `refresh_investments`.
**Liabilities:** `get_liabilities`.
**Assets/Credit:** `create_asset_report`, `get_asset_report`, `get_asset_report_pdf`, `refresh_asset_report`, `filter_asset_report`, `remove_asset_report`, `create_asset_report_audit_copy`, `remove_asset_report_audit_copy`.
**Income Verification:** `create_plaid_user` (`/user/create`), `get_bank_income`, `get_payroll_income`, `get_employment`, `refresh_payroll_income`.
**Transfer (ACH/RTP/FedNow):** `create_transfer_authorization`, `cancel_transfer_authorization`, `create_transfer`, `cancel_transfer`, `get_transfer`, `list_transfers`, `list_transfer_events`, `sync_transfer_events`, `get_transfer_capabilities`, `create_recurring_transfer`, `cancel_recurring_transfer`, `get_recurring_transfer`, `list_recurring_transfers`, `create_transfer_refund`, `cancel_transfer_refund`, `get_transfer_refund`, `get_transfer_metrics`, `get_transfer_configuration`.
**Signal:** `evaluate_signal`, `report_signal_decision`, `report_signal_return`, `prepare_signal`.
**Balance (real-time):** `get_realtime_balance` (=`/accounts/balance/get`, отдельно от Ярус 1 list_accounts).
**Monitor (Watchlist Screening):** `create_individual_screening`, `get_individual_screening`, `list_individual_screenings`, `update_individual_screening`, `list_individual_screening_history`, `create_individual_screening_review`, `list_individual_screening_reviews`, `list_individual_screening_hits`, зеркально для entity: `create_entity_screening`, `get_entity_screening`, `list_entity_screenings`, `update_entity_screening`, `list_entity_screening_history`, `create_entity_screening_review`, `list_entity_screening_reviews`, `list_entity_screening_hits`, `get_screening_program`, `list_screening_programs`.
**Processor tokens:** `create_processor_token`, `set_processor_token_permissions`, `get_processor_token_permissions`.
**Webhook management:** `update_item_webhook`, `get_webhook_verification_key`.
**Sandbox / Testing (только пока environment=sandbox):** `sandbox_create_public_token`, `sandbox_reset_item_login`, `sandbox_fire_webhook`, `sandbox_set_verification_status`, `sandbox_create_transactions`.

## 5. Ярус 3 — функции, придуманные нами для повышения эффективности

Значимое дополнение по стандартной формулировке Влада «для повышения эффективности внутри нашего приложения»:

1. **`audit_connections_health`** — агрегированный отчёт по всем подключённым Item: сколько в `ITEM_LOGIN_REQUIRED`/error-состоянии, сколько давно не синхронизировали транзакции, у скольких Item истекает consent (`PENDING_EXPIRATION`/`PENDING_DISCONNECT`) — value-add health-дэшборд, паттерн уже применённый в Cin7/ShipStation/PagerDuty/GitLab-коннекторах этого портфеля.
2. **`bulk_refresh_transactions`** — форс-рефреш транзакций сразу по нескольким Item одним вызовом (по аналогии с bulk_* в GitLab/CircleCI/UiPath коннекторах).
3. **`bulk_remove_items`** — массовое отключение банков одним вызовом.
4. **`get_spending_summary`** — читает `/transactions/sync` и агрегирует расходы по категориям/мерчантам за период — готовый отчёт вместо сырого потока транзакций.
5. **`get_net_worth_snapshot`** — объединяет `/accounts/get` (депозитные/кредитные счета) + `/investments/holdings/get` (если продукт включён) в один net-worth отчёт по всем подключённым Item пользователя.
6. **`find_recurring_transactions`** — детектор повторяющихся платежей (подписки) по истории `/transactions/sync` — Plaid сам не даёт recurring-детектор в этих продуктах без Income-специфики, поэтому строим эвристику внутри коннектора (группировка по merchant+сумме±5%+интервалу).
7. **`check_transfer_readiness`** — комбинирует `/auth/get` + `/signal/evaluate` в один preflight-вызов перед созданием Transfer — снижает риск отказа платежа одним вызовом вместо двух отдельных.

---

## 6. Тип аутентификации Plaid

Два ключа (`client_id` + `secret`) на HTTP-заголовках `PLAID-CLIENT-ID`/`PLAID-SECRET`, ЛИБО в теле запроса. **Два раздельных окружения (`environment`): `sandbox.plaid.com` и `production.plaid.com`** — Item нельзя перенести между ними, поэтому `connect_plaid` обязан спрашивать `environment` явно и хранить его как часть connection record (аналогично `sandbox`/`live` в Stripe-коннекторе этого портфеля).

Отдельно — `access_token` per Item (одно банковское подключение = один Item = один access_token), получаемый через Link-флоу (`link_token` → пользователь проходит Link на фронтенде/через Hosted Link → `public_token` → `/item/public_token/exchange` → `access_token`). **Наш коннектор не рендерит сам Plaid Link UI** (это iframe/SDK на стороне клиента Plaid) — коннектор предоставляет `create_link_token` для инициализации и `exchange_public_token` для завершения, аналогично тому, как OAuth-коннекторы в портфеле (HubSpot/Shopify и др.) не рисуют форму провайдера сами.

## 7. Явно исключено из этого захода (Not Finished / открытые вопросы)

- **Beacon** — весь продукт помечен `(Deprecated)` в официальных доках Plaid на дату discovery (2026-08-22). Не реализуем активные вызовы; при необходимости можно добавить позже, если Plaid снова его развернёт.
- **CRA / Plaid Check (Consumer Report, cra_base_report, cra_income_insights, cra_lend_score, cra_qualify, cra_home_lending и т.п.)** — регулируется федеральным законом США о защите потребителей (FCRA) как "consumer reporting agency" продукт, требует отдельного юридического одобрения Plaid по контракту и специального разрешительного режима для клиента (не просто API-ключ) — вне стандартного self-serve объёма коннектора. Исключаем сознательно; следующий заход по Plaid может расширить сюда, если Влад подтвердит бизнес-необходимость и юридическую готовность.
- **Employment (`/credit/employment/get`)** — bundled внутри Income Verification продукта, требует того же `/user/create` User API онбординга что и остальной Income-блок; включён в Ярус 2 (`get_employment`) как часть общего Income-потока, отдельно не выделяем.
- **Plaid Layer** (ускоренный onboarding-флоу, комбинирующий Identity Verification + Link) — управляется в основном через клиентский SDK токен-флоу, не имеет отдельной содержательной server-side API поверхности за пределами `/session/token/create`, которая уже упомянута как "see also" у Link — не выносим в отдельный Tier, слишком тонкий срез для этого захода.

Все эти исключения — сознательные архитектурные решения на основе официальной документации, не пропуски по незнанию.

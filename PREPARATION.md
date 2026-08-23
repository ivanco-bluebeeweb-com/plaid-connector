# Plaid Connector — Preparation

**Статус:** Фаза 1-2 (Discovery + архитектурные решения) завершены. Влад
заявил объём разработки прямым поручением 2026-08-22 — «разработай это
приложение в максимальной форме со всеми доступными функциями с их
стороны и всеми возможными функциями внутри нашего приложения для
повышения эффективности» — что закрывает Шаг 5
`CONNECTOR_DISCOVERY_STANDARD.md` (объём = Ярус 1+2+3, без дополнительного
запроса подтверждения).

**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-22, v0.1
**Vikunja task:** оформляется по образцу задач #2149/#2143 (BBW Imperal Apps).

**Почему сейчас:** Plaid — крупнейший финтех-агрегатор Open Banking API
(США/Канада/Европа). Портфель Imperal уже покрывает платежи (Stripe),
CRM/ERP (Salesforce/HubSpot/Cin7), но не имеет ни одного коннектора к
вертикали «банковские данные и денежные переводы через агрегатор» —
Plaid закрывает эту нишу первым и открывает сценарии для финтех-стартапов,
кредитных/лендинговых продуктов и личных финансовых дашбордов на Imperal.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «Plaid»**. Внутренний
app_id/папка: `plaid-connector`.

**Plaid Connector** — коннектор к Plaid API (Link/Items/Accounts/
Institutions/Transactions/Auth/Identity/Investments/Liabilities/Assets/
Income/Transfer/Signal/Monitor/Processor tokens/Sandbox). BYOK: пользователь
подключает свой собственный Plaid-аккаунт (`client_id`+`secret`, отдельно
для Sandbox и Production окружений). Imperal ничего не хостит и не
проксирует помимо самого запроса; Plaid Link (frontend iframe/SDK)
остаётся на стороне клиента — коннектор даёт `create_link_token` /
`exchange_public_token`, не рисует форму провайдера сам (тот же паттерн,
что HubSpot/Shopify OAuth-коннекторы в этом портфеле).

## 2. Проблема в человеческих словах

Когда **разработчик финтех-продукта или команда, строящая
кредитный/бюджетный/платёжный сценарий поверх Imperal**, сталкивается с
**необходимостью получить банковские данные пользователя (счета, баланс,
транзакции, доход) или инициировать перевод денег**, ей приходится
**писать отдельную интеграцию с Plaid REST API вручную, разбираться в
Link-токенах, курсорной синхронизации транзакций, множестве продуктовых
доменов (Transfer/Signal/Monitor и т.д.) и вебхуках с JWT-подписью**, из-за
чего возникает **долгий цикл разработки, риск неправильной обработки
курсоров/вебхуков, и невозможность быстро прототипировать финансовые
сценарии внутри агентных флоу Imperal**.

## 3. Пользователи

- Разработчики финтех/personal-finance приложений, строящие поверх Imperal.
- Команды, которым нужен быстрый доступ к банковским данным клиента для
  KYC/лендинга/бюджетирования без написания собственного Plaid SDK-слоя.
- Внутренние агентные сценарии Imperal (например связка с Budget Studio),
  которым нужны реальные банковские транзакции/балансы пользователя.

## 4. Как сейчас решают эту проблему (без коннектора)

Пишут интеграцию напрямую на Node/Python Plaid SDK, хостят свой backend
для Link-токенов и вебхуков, вручную реализуют курсор-based sync и
retry-логику `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`. Для каждого
нового продукта Plaid (Transfer, Monitor, Income) — отдельный цикл
изучения документации и тестирования в Sandbox.

## 5. Архитектурное решение — BYOK, `client_id`+`secret` пара, окружение как обязательное поле

**WHY BYOK**, как и все connector-приложения портфеля
(Shopify/HubSpot/Salesforce/Stripe/PagerDuty и т.д.): Plaid-аккаунт —
собственность пользователя, Imperal не может и не должна централизованно
брокерить доступ к чужим банковским данным (регуляторные и security
причины делают это неприемлемым).

**WHY `environment` — ОБЯЗАТЕЛЬНОЕ поле подключения, не опция.**

Plaid имеет два полностью изолированных окружения: `sandbox.plaid.com`
(тестовые Item, без реальных банков) и `production.plaid.com` (реальные
данные). Item нельзя перенести между ними. Один и тот же `client_id`
работает в обоих окружениях, но `secret` — разный на каждое. Коннектор
хранит `environment` как явную часть каждой connection-записи (аналогично
`sandbox`/`live` полю в Stripe Connector этого портфеля) — иначе легко
случайно вызвать production-эндпоинт с sandbox-секретом (или наоборот) и
получить непонятную ошибку авторизации.

**WHY `access_token` хранится отдельно от `client_id`/`secret`, per-Item.**

Одно банковское подключение (один логин пользователя в одном банке) =
один Item = один `access_token`, полученный через `/item/public_token/
exchange` уже ПОСЛЕ того как пользователь прошёл сам Link-флоу на
фронтенде/Hosted Link. Коннектор не может создать `access_token` сам по
себе без прохождения Link — только подготовить `link_token`
(`create_link_token`) и завершить обмен (`exchange_public_token`) после
получения `public_token` от вызывающей стороны.

**Паттерн реализации:** ctx-based secrets, как в Cin7 Core / PagerDuty /
CircleCI коннекторах (`_load_connections(ctx)` / `_save_connections(ctx,
...)` / `_resolve_connection(ctx, connection_id)`), `ActionResult.success(...)`
/ `ActionResult.error(...)` (НЕ `.ok(...)` — тот метод не существует в
`imperal_sdk.ActionResult`, подтверждено инспекцией нескольких версий SDK
в рамках предыдущих коннекторов этого портфеля, см. known-bug-patterns.md).

## 6. Границы (что явно НЕ входит в этот заход)

См. `CONNECTOR_DISCOVERY.md` §7: Beacon (deprecated), CRA/Plaid Check
consumer-report серия (регуляторный FCRA-режим, требует отдельного
одобрения Plaid), Plaid Layer (тонкий client-side SDK флоу без
самостоятельной server-side поверхности за пределами `/session/token/
create`).

## 7. CONNECTOR_DISCOVERY — ссылка

Полный трёхъярусный discovery: `Apps/Plaid Connector/CONNECTOR_DISCOVERY.md`.
Ярус 1 (9 функций P0: connect/disconnect/list_connections, create_link_token,
exchange_public_token, get_item/remove_item, list_accounts/get_balances,
sync_transactions, list/search/get institutions, refresh_transactions).
Ярус 2 (~50 функций: Auth/Identity/Investments/Liabilities/Assets/Income/
Transfer/Signal/Monitor/Processor tokens/Webhook management/Sandbox).
Ярус 3 (7 value-add функций: audit_connections_health,
bulk_refresh_transactions, bulk_remove_items, get_spending_summary,
get_net_worth_snapshot, find_recurring_transactions, check_transfer_readiness).

## 8. P0 — минимальный законченный полезный путь

**Главный use case:** подключить свой Plaid-аккаунт → создать Link Token →
(после того как пользователь прошёл Link на своей стороне и получил
`public_token`) обменять его на `access_token` → увидеть счета, баланс и
синхронизировать транзакции этого банковского подключения.

**Сущности/действия без которых результат невозможен:** `connect_plaid`,
`create_link_token`, `exchange_public_token`, `list_accounts`,
`sync_transactions`.

**Server-side safety gates:** любая функция, требующая `access_token`
(т.е. почти всё после Item-уровня) — явная ошибка с понятным сообщением,
если Item не найден/не подключён. Transfer-функции (реальное движение
денег) — не блокируются доп. подтверждением на уровне коннектора сверх
того что уже требует сам Plaid API (`/transfer/authorization/create` →
`/transfer/create` — двухшаговый процесс самого Plaid, это уже встроенный
safety gate).

**Сознательно исключено из P0:** Transfer/Monitor/Assets/Income — Ярус 2,
не блокируют P0-demo.

**Acceptance criteria:** пользователь подключает sandbox Plaid-аккаунт,
создаёт Link Token, эмулирует Link через `sandbox_create_public_token`
(без реального банка), обменивает токен, видит счета и транзакции.

## 9. UX-карта Imperal panel

Точка входа — стандартная карточка приложения в Marketplace → форма
подключения в левом сайдбаре (`client_id`+`secret`+`environment`) по
`UI_INTERFACE_STANDARD.md` (лейблы у всех полей, контекстные плейсхолдеры,
форма растянута на всю ширину сайдбара, никаких карточек-контейнеров,
инструкция — в кнопке+модалке, не дублируется текстом в сайдбаре, «App
settings» — последний элемент внизу). Первый экран после подключения —
список подключённых Item (банковских подключений) с их статусом. Primary
next action — «Create Link Token» → далее взаимодействие идёт через сами
tool-вызовы (create_link_token/exchange_public_token), т.к. сам Plaid Link
UI не рендерится внутри Imperal panel (клиентский SDK стороннего сервиса).
Ошибки — из `error_code`/`error_type` Plaid API, транслируются в понятный
текст. Результат виден в панели через списки счетов/транзакций/отчётов.

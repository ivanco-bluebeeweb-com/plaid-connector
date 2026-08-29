# Plaid Connector — UI component plan

Источники: `Docs/session-notes/UI_COMPONENT_VOCABULARY.md`, `UI_INTERFACE_STANDARD.md`,
`concepts/panels.md`. Основано на функционале `plaid-connector`.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Column`(align="start") + `ui.Text`(environment: sandbox/production) + `ui.Divider` + navigation `ui.ListItem`(Linked Items/Transactions/Identity/Income) + `ui.Button`("App settings") | Без карточек по стандарту; окружение sandbox/production как контекстная метка сверху критична для fintech. |
| Linked Items List (center, `center_overlay=True`) | `ui.Stats`(Linked accounts/Items needing re-auth/Total balance) + `ui.DataTable`(institution, accounts count, status Badge good/login_required/error, linked date; sortable) | `DataTable` — обзор всех Plaid Items (банковских связей) пользователей с индикатором проблем подключения. |
| Item Detail | Back-button + `ui.KeyValue`(institution/webhook status/last synced) + `ui.DataTable`(accounts: name, type, mask, balance; sortable) + `ui.Button`("Force Refresh") | `KeyValue` для метаданных Item, `DataTable` для списка счетов внутри Item. |
| Re-auth Required Alert | `ui.Alert`(variant="warn", "Требуется повторная авторизация в банке") + `ui.Button`("Обновить через Link") | `Alert` — прямое попадание для флага `ITEM_LOGIN_REQUIRED`, критичного статуса Plaid. |
| Transactions Viewer | `ui.Select`(account_filter) + `ui.DataTable`(date, merchant, amount, category Badge, pending Badge; sortable) | Табличный обзор транзакций по счёту с категоризацией. |
| Identity Verification Detail | Back-button + `ui.KeyValue`(name/address/status match — permitted fields) + `ui.Badge`(match result per field) | `Badge` наглядно показывает результат сверки (match/no match) по каждому полю identity. |
| Income/Asset Report Viewer | `ui.KeyValue`(summary: verified income/employer) + `ui.DataTable`(paystubs/transactions использованные для расчёта) | Составной отчёт о доходах — сводка + подтверждающая таблица. |
| Webhook Log | `ui.DataTable`(webhook_type, item_id, received_at, status Badge; sortable) | Диагностика доставки вебхуков Plaid. |
| App Settings | `ui.Accordion`([Connections+Disconnect, Client ID/Environment Config, Webhook URL]) | Централизованные настройки по стандарту. |

## 2. User flow (валидно по panel lifecycle)

1. **SESSION INIT** → `__panel__plaid_sidebar` рендерит окружение + разделы,
   `auto_action` открывает Linked Items List.
2. Linked Items List: DataTable, `status Badge` сразу показывает Items, которым
   нужна реавторизация → клик на строку → `ui.Call(item_id=...)` → Item Detail
   на том же center handler.
3. Item Detail: если статус `login_required` → `Alert` вверху + кнопка
   "Обновить через Link" (открывает Plaid Link во внешнем окне — за пределами
   SDK, задокументировано отдельно в интеграционных заметках).
4. "Force Refresh" → `ui.Call` → `refresh_transactions` → `refresh_panels`
   (обратимое, безопасное действие — без Dialog).
5. Из сайдбара → Transactions/Identity/Income — каждый открывает свой раздел
   на том же center handler с новым `view` параметром.
6. "App settings" (нижняя кнопка сайдбара) → отдельный center handler
   `panels_settings.py` с `Accordion`; "Disconnect" там же — единственное
   деструктивное действие, обёрнуто в `Dialog`.

## 3. Экраны/карточки (конкретно)

- **Screen: Linked Items** — Stats(3) + DataTable(institution/accounts/status/linked_date).
- **Screen: Item Detail** — KeyValue(institution meta) + Alert(если login_required)
  + DataTable(accounts) + Button(Force Refresh).
- **Screen: Transactions** — Select(account) + DataTable(date/merchant/amount/category/pending).
- **Screen: Identity Detail** — KeyValue(matched fields) + Badge per field.
- **Screen: Income/Asset Report** — KeyValue(summary) + DataTable(supporting data).
- **Screen: Webhook Log** — DataTable(webhook_type/item_id/received_at/status).
- **Screen: App Settings** — Accordion(Connections, Config, Webhook URL).

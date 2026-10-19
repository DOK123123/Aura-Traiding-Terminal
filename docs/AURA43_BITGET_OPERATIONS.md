# Aura 4.3 Active Paper v3 — Bitget USDT-M Futures

Отдельный виртуальный BTCUSDT-портфель. Никаких реальных ордеров, account/private
Bitget API, trading API keys или Live Trading. По умолчанию OFF.
Production не обновляется автоматически; миграция здесь не применялась.

Код подготовлен от актуального main после объединения PR #15. Main остаётся
неизменным. v3 заменяет источник **только внутри Aura 4.3**: независимые Aura 4.2,
Paper Practice, Bybit Demo/preview, Bitget/BingX diagnostics и основной Spot-график
не переключаются. Старые счета/история не конвертируются в Bitget.

## Источник и свечи

Единственный host: `https://api.bitget.com`, только фиксированные публичные GET:

| Путь | Назначение |
|---|---|
| `/api/v2/public/time` | биржевое время |
| `/api/v2/mix/market/contracts` | параметры BTCUSDT perpetual |
| `/api/v2/mix/market/ticker` | last price / mark price |
| `/api/v2/mix/market/history-candles` | закрытые исторические last-trade OHLCV |

Для mix-запросов всегда `symbol=BTCUSDT`, `productType=USDT-FUTURES`.
Проверяются base BTC, quote USDT, perpetual, normal и USDT margin, а также
поля возвращаемого символа/продукта, если присутствуют. Spot endpoints, другой
продукт/символ, host override, redirects и private/order paths запрещены.
Нет fallback на Bybit, Binance, Spot или синтетические цены.

Identity: exchange `BITGET`, market_type `USDT_PERPETUAL`, product_type
`USDT-FUTURES`, symbol `BTCUSDT`, settlement `USDT`.
Версия: `AURA_4.3_ACTIVE_PAPER_3`; epoch: `ACTIVE43_BITGET_*`.

Интервалы `15m`, `1H`, `4H` (сохранён и 5m). UTC interval alignment и непрерывное
окно 1000–1288 свечей. Не используются открытые свечи или будущие значения.
Ключевая проверенная особенность Bitget: `endTime` округляется вниз, поэтому
используется **точная граница закрытия**, не `boundary-1ms` — иначе пропускается
последняя закрытая свеча. История приходит по возрастанию, до 200 строк/страницу.
Запрос охватывает не больше 200 интервалов; максимум 8 страниц/1300 свечей.
BTC volume берётся из поля 5, не из USDT turnover в поле 6.

Проверяются exchange `serverTime`, response `requestTime` и ticker `ts`: не
старше 10 секунд, допустимое опережение часов не более 3 секунд. После загрузки
и анализа проверяется неизменность последней закрытой границы. NaN, Infinity,
нулевые/отрицательные/невозможные OHLC, конфликтующие дубли, gaps и невалидная
последовательность не становятся входом. Источник, cutoff, config и hash окна
идут до сохранённого решения. HTTP 403/451/429, business error при HTTP200,
тайм-ауты и повреждённые ответы — контролируемые причины блокировки.

Публичный API из **локального проверочного окружения** реально вернул HTTP200,
контракт и полные окна 15m/1h/4h, а также свежую last/mark котировку. Это не
проверка доступа с Render. Исходные наблюдения и дата в machine report.
В этих read-only запросах нет портфеля, баланса или создания сделки.

## Стратегия, риск и модель исполнения

Donchian 15m остаётся фиксированной стратегией из v2, без оптимизации:
close выше предыдущих 20 high для LONG, ниже предыдущих 20 low для SHORT;
ATR14, SL 2 ATR, TP 4 ATR, exit channel 10. Индикаторные формулы/пороги не
изменяются ради частоты. 1h/4h поддерживаются адаптером; новый обязательный
MTF-фильтр не добавляется. Aura 4.2 strategy/risk/scheduler не меняются.

Используются те же network-free production Decimal функции: sizing, virtual
fill, fees, liquidation equity, SL/TP, close и PnL. Учёт **closed-signal /
next-open OHLC**: сигнал закрытой свечи сохраняется, следующая open-цена
учитывается после закрытия следующей свечи. Это виртуальная OHLC-модель,
не мгновенный рыночный ордер и не обещание исполнения по живому тикеру.
При двойном касании SL+TP — SL; gap SL по adverse open; gap TP консервативно.
Динамический ATR stop, где предусмотрен стратегией, действует только далее.

- Один новый виртуальный баланс 10000 USDT; существующий не сбрасывается.
- Риск с комиссиями/SL-slippage ≤0,5%, дневной loss stop 2%, DD stop 10%.
- Не больше одной позиции; notional ≤2000 USDT.
- Проверенные Bitget qty step/minQty `0.0001 BTC`, min notional `5 USDT`,
  price tick `0.1 USDT`. Frozen bounds сравниваются с реальным contracts API;
  несовпадение блокирует новые входы. Максимальный market quantity проверяется.
- QTY округляется вниз; SL/TP приводятся к tick, риск считается заново.
- Сохранена консервативная модель v2: fee 0,10% и slippage 0,05% на сторону.
  Это не тариф аккаунта Bitget. Публичный taker/maker metadata не заменяет
  неизвестный account tier. Funding/margin/liquidation/orderbook/latency не
  моделируются. Нет утверждения о полной futures-доходности или прибыльности.
- Риск-stop — запрет входов, не гарантированный потолок gap-убытка.

Текущая цена/PNL в UI read-only и не исполняют сделки. Старый Spot backtest
помечен архивом; его цифры не относятся к Bitget. `UNVALIDATED_FUTURES`.

## Хранилище, восстановление и ошибки

Новая схема: **`scripts/active43_bitget_schema.sql`**.
Новые account/events/RPC/functions/indexes/trigger только `aura_active43_bitget_*`.
Старые `aura_auto42_*`, `aura_practice_*`, `aura_active43_*` и
`aura_active43_bybit_*` не используются новым Store и не изменяются миграцией.
Старую Bybit SQL для нового портфеля применять не надо.

RLS и запрет anon/authenticated table/RPC; service_role только на сервере.
Новый Store имеет закрытый allowlist трёх Bitget RPC. Account/events/watermark,
ON/OFF, pending и idempotency keys фиксируются одной SQL транзакцией.
SHA256/checksums, row lock/CAS, unique IDs и commit-time OPEN freshness.
Повторный load не сбрасывает баланс. Ошибка БД не подтверждает открытие.
Потерянный ответ после commit восстанавливается receipt/readback, без вторых fees.

После рестарта читаются ON/OFF/позиция/epoch из SQL, не из браузера. Во время
сбоя API входы приостанавливаются, причина сохраняется при доступной БД.
Возобновление возможно только для ранее включённого режима после свежих данных
без risk-stop. STOP/EMERGENCY не самоснимаются. Старые pending при пропусках
отбрасываются; новые сделки задним числом не создаются. Доступные закрытые
свечи могут защитить старую позицию; отсутствующая история не выдумывается.
При correction/watermark вне bounded window требуется review владельца.

`last_run_at` — последний сохранённый tick, даже с source error;
`last_successful_run_at` — последний сохранённый tick без ошибки;
`last_success_at` — последние успешные market data. Ошибка БД не сохраняет
ложное подтверждение. Все даты и причины доступны owner UI/API.

## Переменные Render (только после разрешения владельца)

| Переменная | Назначение |
|---|---|
| `AURA_ACTIVE43_ENABLED=true` | общий opt-in модуля |
| `AURA_ACTIVE43_BITGET_ENABLED=true` | отдельное согласие на v3 Bitget |
| `AURA_ACTIVE43_BITGET_SUPABASE_URL` | HTTPS URL существующего Supabase проекта |
| `AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY` | server-only service_role key |
| `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` | новый случайный ASCII token ≥32 символов |
| `AURA_TESTNET_VIEW_PASSWORD` | существующий owner password; не менять |

Старые Bybit/Auto42/Practice env не переименовывать и не удалять. Они не
активируют v3. Bybit scheduler token повторно использовать запрещено.
Bitget API key/secret/passphrase не нужны и кодом не читаются.
Даже с этими env первый аккаунт OFF до отдельного owner START.
`RENDER`/`RENDER_GIT_COMMIT` предоставляет платформа — не подделывать их.

## GitHub Actions

Файл `.github/workflows/aura-active43.yml`, новый job guard
`vars.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED == 'true'`.
Secret: **`AURA_ACTIVE43_BITGET_SCHEDULER_SECRET`**, совпадает с новым Render token.
Cron `2-59/5 * * * *` и ручной `workflow_dispatch`; отдельная concurrency group
`aura-active43-bitget`, cancel-in-progress=false. URL фиксирован:
`https://aura-traiding-terminal.onrender.com/api/active43/tick`.
Header **`X-Aura-Active43-Bitget-Token`**, отдельный от Bybit/Auto42.
Ответ проверяется по source=Bitget и version=v3. Старый Bybit job не может
авторизоваться в v3, а новый — в старом runtime. Source/версия не маскируются.

В браузере нет scheduler secret. Нет второго in-process scheduler v3.
Повторные/параллельные HTTP ticks защищены также SQL/CAS/immutable bucket ID.
Статус FRESH показывает недавний сохранённый tick, а не гарантию наличия сигнала.
Actions schedule работает из default branch и best effort; бесплатный Render
может засыпать. Непрерывная работа 24/7 и своевременное SL/TP при простое не
гарантируются. Paper-стопы не находятся на бирже.

## Безопасный запуск владельцем: сейчас не выполнять автоматически

1. Review нового PR; merge/deploy только отдельно владельцем. Render Auto-Deploy
   по сообщению владельца отключён; его настройки здесь не менялись.
2. Если Bybit v2 уже использовался, перед заменой runtime запретить его входы и
   убедиться, что его позиция закрыта. Не переносить её/баланс в v3 и не оставлять
   старую позицию без старого мониторинга. Если v2 не запускался — ничего сбрасывать не надо.
3. Сделать backup. В SQL Editor Supabase просмотреть и применить **только весь
   `scripts/active43_bitget_schema.sql`**. Он в BEGIN/COMMIT, повторное применение
   проверяется локально. Требуется существующий pgcrypto в extensions; не
   перемещать старое extension. Торговые таблицы/счета не удалять.
4. Задать отдельные env из таблицы. Существующий entrypoint `python start_web.py`,
   PORT и остальные настройки не менять. Выполнить ручной deploy разрешённого SHA.
5. Проверить `/api/health`, owner login `/api/paper/login`, затем отдельный блок
   **AURA 4.3 ACTIVE PAPER v3 / Exchange BITGET / Market BTCUSDT USDT-M Futures**.
   Подтвердить первый OFF/10000 и SOURCE Bitget, чтение SQL. При ошибке схемы/БД
   не нажимать START и не сбрасывать старые счета.
6. Проверить **именно с Render** доступ к Bitget time/contracts/ticker/history.
   Свежая котировка UI не доказывает полноту истории. START сам проверяет полное
   закрытое окно и frozen filters и при отказе не включает режим. 403/429/timeout,
   stale/missing candles должны блокировать входы; обходов/подмен нет.
7. Настроить новый Actions secret/variable. Сначала `workflow_dispatch` при OFF:
   проверить сохранённый tick и FRESH. Это не сделка. Старые scheduler не менять.
8. Явно подтвердить `START EXPERIMENTAL PAPER`. Это baseline со свежей свечи,
   не приказ открыть позицию. `NO_SIGNAL` допустим; искусственных production
   сигналов/ручного OPEN в этом модуле нет.
9. Закрыть браузер, подтвердить несколько сохранённых внешних ticks. Проверить
   рестарт Render: тот же epoch/баланс/позиция/ON-OFF, без дублирующего OPEN.
10. Ждать естественного сигнала не нужно бесконечно: технический цикл доказан
    изолированно. Но `PRODUCTION_PAPER_VERIFIED` возможен только по настоящему
    native SIGNAL→OPEN→UPDATE→CLOSE с source Bitget, Render SHA и SQL receipt.
    Локальные тесты и публичный probe не устанавливают этот статус.

Read-only SQL для сверки после разрешённого владельцем запуска:

```sql
SELECT revision,saved_at,payload::jsonb->>'market_source' AS source,
 payload::jsonb->>'mode' AS mode,payload::jsonb->>'balance' AS balance,
 payload::jsonb->'position' AS position,payload::jsonb->>'last_run_at' AS last_run,
 payload::jsonb->>'last_successful_run_at' AS last_successful_run
FROM public.aura_active43_bitget_account WHERE id=1;

SELECT seq,kind,created_at,payload::jsonb->'payload' AS event
FROM public.aura_active43_bitget_events ORDER BY seq DESC LIMIT 100;
```

STOP запрещает входы, но для защитного закрытия оставить feature/scheduler
доступными. Не выключать весь runtime с открытой позицией. Rollback: STOP,
отсутствие v3 позиции, отключить только новый job/flags и вернуть прошлый SHA.
Новые таблицы/историю не удалять, не переносить в Bybit. EMERGENCY/DD stop не
снимаются автоматически или через reset API (его нет).

## Проверки и воспроизведение

```bash
python -m pytest -q
node tests/test_active43_frontend.cjs
python -m scripts.verify_active43_postgres --output /tmp/bitget-pg.json
python -m scripts.verify_active43_browser --output /tmp/bitget-browser.json
```

Полный прогон включает все `tests/*.cjs` и opt-in переменные
`AURA_PRACTICE_VERIFY_POSTGRES=true`, `AURA_AUTO42_VERIFY_POSTGRES=true`,
`AURA_ACTIVE43_VERIFY_POSTGRES=true`. В managed sandbox используется только
test wrapper `enable_sandbox_poll()`; production event loop не меняется.
PostgreSQL 16 — одноразовый local Docker, network none, no ports, 512MiB/1CPU.
Проверяются повторное применение SQL, роли/RLS, транзакции/rollback, конкуренция,
неизвестный исход commit, restart/outage, дубли OPEN/CLOSE и независимый Decimal oracle.
Сравниваются старые account/event hashes **и определения старых SQL функций**.

Два полных native-indicator LONG/SHORT сценария используют контролируемые
Bitget V2 fixtures → авторизованный HTTP tick → production Market/Service/engine
→ реальные local SQL RPC → owner API. Синтетика только в tests/scripts,
никогда в production. Браузер отдельно проверяется реальным Chromium на 430px.
Mock HTTP bridge к реальному PostgreSQL не является hosted PostgREST/JWT proof.
CLI не принимают production DSN/key и отказываются работать при RENDER.

Финальные результаты, хэши, local SQL cases, public smoke и отдельные
code/security review: `docs/AURA43_BITGET_VERIFICATION.json`.

Новых платных ресурсов/API нет. Существующий Supabase Free можно использовать
с отдельными таблицами; фактические quotas/headroom и тариф Render здесь не
доступны. Append-only журнал растёт, нужен контроль места и backup. Service_role
остаётся широким проектным ключом, namespace не заменяет отдельный DB principal.
Никакого merge/deploy/production SQL/активации в этой работе не выполнялось.

## Code/security review

Отдельные self-review проходы по `docs/ecc/TRADING_REVIEW.md`: UTC/closed/causal
анализ, boundary pagination, contract identity, quantity/tick/fee/risk, SQL
атомарность/roles/CAS/readback, restart, owner/CSRF/token, bounded HTTP/CPU,
ошибки/секреты, source/version изоляция и безопасный textContent/SVG UI.
Это не внешняя сертификация и не отдельные AI-агенты.

Особые регрессии: Bitget endTime rounding, ascending 200-row pages, symbolType
perpetual и USDT margin, requestTime/serverTime/ticker ts, HTTP200 business errors,
неверные/NaN/нулевые цены, конфликтующие дубли/gaps/forming, 403/429/timeout,
старые Bybit flags/headers/tokens и сохранение last_successful_run_at при ошибке.
Ни одна контролируемая тестовая сделка не маркируется production VERIFIED.

Доказательства изоляции: неизменность protected trading paths в git и одинаковые
SQL хэши старых account/event данных и function definitions до/после миграции,
повторного применения и сценариев. В старые таблицы новая миграция не пишет.

Перед реальным запуском остаются отдельные release gates: owner review/merge,
ручное применение новой SQL, ручной deploy, фактическая доступность Bitget с
Render, hosted Supabase readback, внешний scheduler без браузера и рестарт.
Проверка естественного OPEN→UPDATE→CLOSE на сервере остаётся отдельной от
технической готовности. Не заявляется, что эти production проверки выполнены.

## Финальные результаты

**1429 Python PASS**, 1 существующее предупреждение; **18 JavaScript suites PASS** (Active43 frontend 16 tests). PostgreSQL: 7 scenarios, 9 check groups, 2 native HTTP cycles. Chromium mobile 430px: PASS. Syntax/import: PASS. Реальный публичный Bitget REST локально: PASS. Render connectivity / production cycle: NOT TESTED.

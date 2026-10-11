# Aura: аудит перед ручным тестированием Render / Android

Аудит исходного main `2973ae9ace07d1a4f9b7612b15843900bfa3a6df`, после добавления
Paper Trading. Выполнены отдельные проходы по ECC/Aura guidance одним исполнителем;
это не утверждение о запуске отдельных агентов. Изменения ограничены доказанными
ошибками, regression tests и этим отчётом. Запросы к биржам с credentials,
реальная торговля, новые функции и платные сервисы не использовались.

## Девять review-проходов

| Проход | Проверенные границы / результат |
|---|---|
| Architecture | Публичные market-data, indicators, historical research, read-only accounts и локальный paper ledger разделены. Paper получает только injected public-market callback. Core/storage/models без network dependencies. Один worker SQLite; масштабирование не добавлялось. |
| Python/FastAPI | Lifespan, async locks/cancellation, worker-thread SQLite, auth, CSRF, строгие DTO, safe errors проверены. Ошибки startup SQLite исправлены; повреждённый paper journal не ломает health/главную страницу. |
| Frontend/JavaScript | Market/source/timeframe races, повторные действия, idempotent pending retry, loading/error, безопасный textContent проверены. Исправлены stale Paper state и возврат из back-forward cache. |
| Security | Проверен путь от Paper/strategy до клиентов: нет exchange-writing paths, production account host override или автоматического execution switch. Owner/CSRF и Demo credential isolation сохранены. |
| Trading math | Независимые Fraction-эталоны с собственным integer-tick округлением: LONG/SHORT, обе комиссии, balance/equity, risk bound, size precision, PF/win rate/DD/return. Дополнительно ручные EMA/RSI/ATR эталоны. Ошибка historical DD воспроизведена и исправлена. |
| Paper Trading | SL/TP, gap/ambiguous/partial-bar model, collateral, max positions, insufficient funds, stale marks, request/signal dedup, backups/restart и corrupt journal проверены. Корректность валидного ledger и replay сохранена. |
| Bybit Demo | Фиксированный официальный Demo V5 host, GET allowlist, HMAC query/header bytes, time sync, single clock retry, rate cooldown, timeout, safe error mapping и output whitelist проверены без live account traffic. Runtime код не менялся. |
| Reliability/error handling | Binance reconnect/backoff/bootstrap, old socket suppression, closed/provisional distinctions, source changes, public/account outages, journal rollback/restore и stale UI проверены. Operational ограничения Render остаются явными. |
| Testing/edge cases | Сначала новые regressions падали на исходной реализации. Затем минимальные fixes, независимые math fixtures, интеграционный corrupt-startup check и полные offline suites. Нет изменения тестов ради скрытия отказа. |

## Подтверждённые проблемы и исправления

| Severity | Проблема / воспроизведение | Исправление |
|---|---|---|
| **HIGH** | `app/paper/engine.py`, `_advance` / `_point`: restart replay оценивал historical mark относительно текущего wall clock. Последовательность 100 -> 90 -> 100 после паузы 5 минут давала max DD **0** вместо **10 USDT**. | Historical point использует момент закрытия replay-свечи, при этом свежесть самой загрузки проверяется по текущему времени. Будущие marks, entry fees и settlements не участвуют в historical equity; при невозможности согласовать ledger точка остаётся null. Regression фиксирует equity 9990 и max DD 10; формулы стратегии не изменены. |
| **MEDIUM** | Startup принимал SQLite с отсутствующим peak, NaN drawdown, неверным close sequence, повреждёнными SL/TP/time/PnL%, расхождением индексного status с JSON, отсутствующим command journal или неверной curve. Это могло дать 500, неверную статистику/защитный exit или потерять dedup после restart. | В одной startup-транзакции проверяются metadata, finite/quantized money, stop direction, time alignment, closed PnL%, индексные поля, FK, command UUID/digest/count, close order и curve/DD consistency. Повреждённый ledger fail-closed; автоматического reset/repair нет. Market health/HTML остаются доступны. |
| **MEDIUM** | `static/paper.js`: скрытая вкладка могла бесконечно показывать старую equity; после `pagehide` polling остановлен без восстановления при bfcache возврате. | TTL снимка 30 с проверяется на timer/visibilitychange; старый panel скрывается до успешного чтения. Pagehide закрывает controls; pageshow перезагружает восстановленную страницу, сохраняя pending command в sessionStorage. Нет автоматического повтора сделки. |

Все перечисленные ошибки подтверждены regression tests. Необоснованные изменения
провайдеров, стратегии, индикаторов, тарифов, account permissions не выполнялись.
Неразрешённых critical/high дефектов в проверенном scope не выявлено; это не
формальная гарантия отсутствия всех ошибок или live-работоспособности Render.

## Trading-math / Paper conclusion

- LONG: `(exit-entry)*size`; SHORT: `(entry-exit)*size`. Из обоих вычитаются
  entry/exit fees. Commission configurable, rate — допущение paper, не тариф биржи.
- Эталон size=1, commission=0.10%: LONG 100 -> 110 = **9.79 USDT**;
  SHORT 100 -> 90 = **9.81 USDT**; SHORT 100 -> 110 = **-10.21 USDT**.
- Entry fee сразу уменьшает balance. При close добавляется gross minus exit fee,
  поэтому entry fee не списывается дважды. Equity включает gross unrealized и
  предполагаемую exit fee. Available balance вычитает 1× reserved collateral.
- Risk budget — процент свежей equity до входа; planned SL loss включает обе
  комиссии. Auto quantity ограничена risk, max notional и свободными средствами,
  floors to 12 digits; независимые actual rounded checks выполняются после sizing.
  Per-trade risk не является лимитом суммарного portfolio risk. Gaps могут превысить
  planned SL loss. Отрицательный виртуальный баланс не вызывает внешнее funding.
- Closed win rate включает breakeven в denominator; PF = сумма net wins / модуль
  суммы net losses. Без losses PF null. Average/RR без необходимых данных null.
  Gross profit/loss в strategy statistics агрегируют net trade outcomes; per-trade
  gross_price_pnl отдельно хранит движение до fees. Open fees не выдаются за closed
  realized loss. Streaks идут по порядку закрытия, breakeven сбрасывает обе серии.
- Деньги Decimal precision 64 / 8 USDT decimal places; fee/notional ceil, price PnL
  half-even; JSON/SQLite financial amounts — строки. Number только для SVG drawing.
- SL/TP: закрытые свечи, first overlapping bar close-only, full later bars OHLC,
  SL first при двойном касании, adverse stop gaps по worse open, favourable TP gap
  по target. Это сознательная documented fill model, не текущий exchange bid/ask.
- Curve/DD sampled liquidation equity, не tick/intrabar. Исправлен single coherent
  replay DD. Несогласуемые historical cashflows/marks остаются gaps, не выдуманной
  реконструкцией. Peak/max DD persist независимо от последних 500 API curve points.

## Bybit / security conclusion

Only host: `https://api-demo.bybit.com`. Only GETs:
`/v5/market/time`, `/v5/account/wallet-balance`, `/v5/order/realtime`,
`/v5/order/history`, `/v5/execution/list`.

HMAC-SHA256 signed payload: `timestamp + api_key + recvWindow + encoded GET query`;
`recvWindow=5000`, API key/time/sign/recv headers and sign type 2. Exact encoded
cursor/query signature is covered by offline tests. Clock uses official time,
request midpoint offset, 5-minute sync cache and one forced retry for clock error.
Individual HTTP timeout 8 s, total snapshot timeout 25 s; redirects disabled.
Cooldown uses Retry-After and Bybit reset timestamp; HTTP/retCode classifications
are numeric allowlisted diagnostics, not raw upstream text.

Credentials only from ENV, repr hidden; secret never goes to browser. Account
outputs whitelisted and checked against credential values; logging guards cover
HTTP client/core/handlers. UI keeps exact amount strings, UNIFIED wallet/equity/
available margin separated, missing values shown —. History is scoped 7 days /
200 records per type, explicitly truncated, not a complete account archive.
No create/amend/cancel/withdraw/transfer/funding methods. No Binance fallback.

Binance Testnet also remains fixed-host GET-only and owner protected. Public
Binance production **quotes** are separate from private-account execution. Static
call/endpoint review found no accessible path for Paper or strategy to send an
exchange write. `REAL MONEY EXECUTION=DISABLED`, automatic strategy entry OFF;
automatic **analysis refresh** is not automatic trading. No credentials changed.

## Market-data conclusion

Candle ordering/count/alignment/OHLCV/duplicate/gap validation precedes analysis.
Binance REST uses closed rows and source-consistent history; WS bootstrap/reconnect
resnapshots and rejects stale/future/regressing events and gaps. Frontend ignores
old socket generations and mismatched symbol/timeframe, disables stale signals and
reconnects silent sockets. Pattern signal is gated by chart source + freshness;
indicators and matching formulas/thresholds were left unchanged.

REST close and provisional WS close are deliberately different price references;
Paper fills only verified REST closed close and labels its reference time/source.
There is no claim that this equals instant live execution. Gold broker sources can
differ and be delayed; their windows replace rather than mix feeds. OANDA feed uses
an unofficial anonymous TradingView protocol, without SLA. XAU is not paper-traded.

## Checks run and limits

- **483 Python tests PASS** (437 baseline + 46 audit cases).
- **52 JavaScript tests PASS** (9 market, 11 Binance, 13 Bybit, 19 Paper).
- All **50 Python files** syntax-parsed; all app modules imported. All local
  JavaScript and Node test files passed `node --check`.
- Static credential scan, paper network-dependency/endpoint scan, API read-only
  boundary tests, HTML assets/IDs/ARIA and responsive CSS structural checks PASS.
  Heuristic secret scan is not a formal exhaustive proof. No .env/actual credential
  fixtures added; no exchange requests with real keys.
- Existing baseline tests include ownership, CSRF, LONG/SHORT profit/loss, commission,
  SL/TP/gap/partial candle, risk/limits/balance, malformed data, same-command/signal
  duplicates, concurrent writes, restart, standalone backup restore, source/stale
  failure, signatures/auth/clock/HTTP/network/rate-limit errors and account UI races.
- pytest 8.3.5 ran from already available temporary dependencies. Plugin/cache
  disabled and a temporary Cloud TestClient event-loop wakeup accommodation was
  used; production event-loop code unchanged. One existing Starlette deprecation
  warning. No packages installed for this audit.
- Installed FastAPI 0.141.1, Uvicorn 0.52.1, HTTPX 0.28.1, websockets 16.0,
  NumPy 2.3.5 differ from requirements pins. Exact pinned Render environment not
  tested here. Requirements reviewed, no new dependency needed; transitive versions
  are not fully locked. No unsupported assertion that dependency CVEs are absent:
  pip-audit/ruff/mypy/bandit unavailable, NOT RUN. Coverage not measured.
- **Full browser/mobile test NOT RUN** in this audit. Prior Chromium attempt was
  blocked by Cloud socket restriction; no bypass/retry/external browser added.
  Responsive CSS/DOM checks do not prove Android layout. Live Render/Bybit
  connectivity and deployment of this commit are not verified by offline tests.

## Неисправляемые этим аудитом operational/model ограничения

Render ephemeral filesystem может потерять SQLite на redeploy/restart, free sleep
останавливает monitoring, `.cache` и публичные archives могут пересоздаваться.
Нужен user-managed persistent disk (`PAPER_DB_PATH`) для долговременного journal
или регулярный owner-only download backup. Никакой платный диск не подключался.
Page reload не удаляет server journal. Один worker; нет distributed execution.
Corrupt journal now blocks paper instead of resetting; восстановление — offline
backup procedure, не web destructive reset. При полном исчезновении ephemeral DB
нет внешнего реестра, позволяющего отличить новое размещение от потери старого.

500-bar replay limit, unavailable history/source correction, no spread/funding/
leverage/slippage model и отсутствие auto entry сохранены. Многотаймфреймовая
historical equity не реконструируется из будущих cashflows. Manual math/strategy
checks не означают доказанную прибыльность или соответствие настоящим fills.

## Завтрашний чеклист Render / Android

1. В Render проверь deployed SHA, Build/Start success (`python start_web.py`),
   отсутствие traceback; `/api/health` -> ok. Не присылай logs/скриншоты с headers
   или credentials. ENV менять/раскрывать для этого аудита не нужно.
2. Android Chrome, портрет и landscape: загрузка всей страницы, читаемые cards,
   настройки без увеличения всей страницы, горизонтальный scroll только внутри
   широких таблиц, Open/Close/Retry доступны без обрезания.
3. BTCUSDT 1m/5m/15m/1h; быстро сменить timeframe и BTC/XAU. Должны совпадать
   symbol/TF/source на графике/сигналах; прежний ответ не возвращает старый рынок.
4. Отключить интернет на телефоне на 30–60 с: stale/reconnect, сигналы отключены,
   Paper Open заблокирован. Включить: новый snapshot/live восстанавливаются без
   дублирования свечей. Не ожидать имитации live, если provider недоступен.
5. Paper login `aura` с существующим owner password. Без входа действия закрыты.
   Сверить Virtual Balance/Equity, комиссии и **AUTO ENTRY OFF / REAL DISABLED**.
6. Get Paper Quote: BTCUSDT/source/TF совпадают с графиком; цена соответствует
   **последней закрытой** свече и её UTC времени, не forming live candle.
7. Маленькая ручная LONG, затем SHORT: entry fee, резервирование available balance,
   net PnL при close, обе комиссии, запись reasons/source/timeframe. Refresh
   страницы сохраняет trade; быстрые повторные taps не создают два одинаковых IDs.
8. Недопустимые size/SL/TP, завышенная позиция и max simultaneous limit: понятный
   отказ, без новой trade/fee. Слишком маленький TP может не покрыть commissions.
9. SL/TP на малой виртуальной позиции: ждать закрытия свечи, проверить documented
   close-only first partial bar и conservative ambiguous/gap rules. Биржевой ордер
   появляться не должен. Не включать automatic strategy execution.
10. Перейти в фон более минуты и вернуться, Back/Forward: просроченная equity не
    остаётся активной, panel обновляется. При unknown action outcome использовать
    **Retry с прежним ID**, не новую сделку; refresh сохраняет pending command.
11. Closed journal, win rate, PF, equity curve: первые пустые показатели — —;
    отсутствие losses не выдаётся за PF=0/бесконечность. При data errors equity —.
12. Bybit Demo: owner login, Connected либо конкретный безопасный error, правильная
    category/symbol, wallet/equity/available margin, empty orders/history как
    отсутствие записей. История on-demand. Увиденный Connected не означает торговлю.
13. Скачать SQLite backup. Restart/recovery проверять только после backup и с
    настроенным persistent storage; не использовать redeploy ephemeral DB как
    тест гарантированной сохранности. Сверить journal/balance/duplicate IDs.

## Changed files

`app/paper/engine.py`, `static/paper.js`, `tests/test_paper_engine.py`,
`tests/test_paper_api.py`, `tests/test_paper_frontend.cjs` — bug fixes/regressions.
New: `tests/test_audit_math.py`, this report. `docs/PAPER_TRADING.md` updates
recovery/curve semantics. No account client, market pipeline, indicator/strategy,
chart JS, backtest, credentials, UI design or dependency changed.

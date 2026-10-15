# Aura 4.2 — Bybit linear: безопасный этап A/B

Дата: 15 октября 2026. База: 912ad6a59b4e34288161e08212cb702b8459af8b.
**Релиз частичный: A/B подготовлены; переключение исполнения и приёмка C–G заблокированы.**
Ни одна новая стратегия или торговый режим не активированы.

## Аудит текущих контрактов

- app/main.py: lifespan создаёт отдельные Auto42, legacy Paper, MarketContext,
  Bybit Demo, Strategy Lab, Forward Validation. Их состояние нельзя объединять.
- app/automated/strategy.py: существующий experimental confirmed BOS/CHoCH + retest;
  15m, согласование 1h/4h, ADX25, ATR stop 1.5, reward2, volatility .65–2.
  Source жёстко Binance Spot, hash всего candle snapshot, подтверждённые закрытые
  свечи, gap check, достаточный warmup. Формулы/пороги не менялись.
- app/automated/engine.py: policy 10000 USDT; риск .5%; max notional2000;
  max1 position; daily loss2%; drawdown10%; fee .10%/side, adverse slip .05%/fill.
  Quantity BTC отделён от notional USDT; текущая модель — 1x collateral virtual,
  НЕ полноценный perpetual margin/liquidation engine. Funding не моделируется.
- Closed-candle next-open execution: pending signal на close, next open применяется
  при получении закрытой execution candle. Не intrabar. SL first при SL+TP,
  stop gap adverse open, TP gap conservatively target. Текущая OHLC — Binance Last.
- service.py: owner preflight/CSRF/CAS; tick singleflight + persisted slot key;
  source/candle watermark; confirmed fresh data; STOP и EMERGENCY не закрывают
  позицию, а запрещают новые входы. Защитные выходы зависят от scheduler и данных.
- Supabase auto42_account/events, append-only journal, row lock/CAS, отдельные
  RPC; legacy SQLite/Replay/Lab не затрагиваются. История не мигрировалась.
- Cloudflare/GitHub каждые5мин не дают мгновенного SL/TP, Render Free может спать.
  Новые модули не могут гарантировать always-on сопровождение.

## Официальные спецификации

Прочитаны публичные документы:
https://bybit-exchange.github.io/docs/v5/market/kline
https://bybit-exchange.github.io/docs/v5/market/tickers
https://bybit-exchange.github.io/docs/v5/ws/connect
https://bybit-exchange.github.io/docs/v5/websocket/public/ticker

Endpoints fixed, без override/redirect:
- HTTPS GET https://api.bybit.com/v5/market/instruments-info
- HTTPS GET https://api.bybit.com/v5/market/tickers
- HTTPS GET https://api.bybit.com/v5/market/kline
- wss://stream.bybit.com/v5/public/linear, topic tickers.BTCUSDT.

Обязательная identity: BYBIT / USDT_PERPETUAL / linear / BTCUSDT / USDT.
Instrument verification требует LinearPerpetual, Trading, quoteCoin=settleCoin=USDT.
Ключи не нужны; private APIs, Bybit Demo credentials и Binance keys не читаются.

## Реализовано

1. app/bybit_linear/client.py: whitelist только трёх GET; identity/contract checks,
   HTTP timeout12s, максимум2 попытки public GET, rate limit cooldown, redirects
   blocked, JSON response ≤1MiB, safe enum errors. HTTP403/451 честно блокирует.
2. OHLCV: 15/60/240 V5 intervals; reverse pages проверяются, затем нормализуются
   chronologically. Timestamps ms → seconds, завершённые UTC bars, Decimal OHLCV,
   volume в BTC (не turnover USDT), идентичные дубли считаются, конфликтные
   отклоняются, пропуски отклоняются без fill. До13000 bars/15pages/60s.
3. app/bybit_linear/feed.py: snapshots/deltas без смешивания reconnect sessions,
   обязательные Last/Mark, server message timestamps, heartbeat20s, reconnect
   backoff1..30s, message limit64KiB, bounded queue, stale10s, REST fallback
   singleflight не чаще15s. Значения свечи не используются вместо live ticker.
4. Защищённый GET /api/bybit-linear/ticker и отдельный read-only UI preview.
   В UI Last, Mark, timestamp ответа/сообщения и транспорт, LIVE/STALE/DISCONNECTED.
   Время последней сделки не выдумывается. При ошибке цена не показывается свежей.
5. Feature flag **AURA_BYBIT_LINEAR_PREVIEW=true**, по умолчанию OFF.
   При OFF network service не создаётся. При true только public data service;
   Auto42 и основной Binance chart НЕ переключаются. UI открывается отдельно,
   polling только когда видим, no execution controls, no API keys.
6. scripts/import_bybit_linear_history.py: CLI-only download в новый .json,
   не в app/ или .data; файл не перезаписывается. 7/30/90days, явный warmup
   4160×15m или250×1h/4h. Identity и checksum в snapshot; недостаток данных — отказ.
   **Это импорт истории, не backtest/replay и не стратегия.**

## Подтверждённая блокировка данных

Публичные GET instruments-info и tickers с category=linear&symbol=BTCUSDT
из рабочей среды вернули **HTTP403**. Точная причина доступа (регион/WAF/IP)
не установлена. Ни proxy/VPN, ни обходные hosts не использовались.
Реальные Bybit snapshots/replay не получены. WS работает только в offline mocks;
подключение из Render и реальный WS не проверены. Нельзя считать, что доступность
Bybit Demo или Binance доказывает доступность Bybit linear.

## Что НЕ реализовано и почему нельзя выпускать переключение

- Production Bybit source selection: запрещено автоматически сменить рынок
  существующих positions/pending/state. Нужен owner-confirmed переход при OFF,
  без позиции/pending, отдельная versioned identity/account migration и rollback.
  В этом commit такой переход отсутствует, source remains Binance Spot.
- Historical Replay production Auto42 на Bybit: strategy пока отклоняет любой
  другой источник. Это защита, а не «адаптация» подстановкой Binance label.
  Не создана похожая стратегия/фейковые доходности; на7/30/90дней результаты не заявляются.
- Futures accounting: funding, variable leverage, mark-triggered stops,
  liquidation/maintenance margin не подключены. Нет доказанного полного реализма.
- Manual close и lines/markers Bybit на основном графике: не добавлены. Для них
  нужны свежая server-side Bybit quote, определённые trigger/fill basis,
  отдельная identity в persistent position, CAS close-vs-stop/idempotency и migration.
  До этого нельзя предложить кнопку, которая закрывает Binance-позицию по Bybit.
- Новый расширенный журнал решений и replay metrics: не подключены; прежний
  Auto42 journal и его события сохранены. Нет нового always-on execution monitor.

Этапы C–G остаются незавершёнными. Это законченная безопасная поставка A/B, а не
объявление выполнения всего приложенного задания. Отсутствие данных не заменено
synthetic profitability results. Перед изменением исполнения потребуется отдельная
проверка спецификаций и source migration; флаг preview не даёт такого разрешения.

## Как проверить preview/импорт

Опционально владелец добавляет в Render Environment только
AURA_BYBIT_LINEAR_PREVIEW=true и делает Deploy. Новые secret/API keys не нужны.
Это включает публичный feed, но не торговлю. Войти владельцем, открыть отдельный
«Bybit BTCUSDT · USDT Perpetual · READ ONLY preview». При403 отображается отказ,
а не fake Last/Mark. Binance chart явно сохраняет свою identity.

```sh
python -m scripts.import_bybit_linear_history --days 30 --timeframe 15m --output /tmp/bybit-30d.json
python -m scripts.import_bybit_linear_history --days 90 --timeframe 15m --output /tmp/bybit-90d.json
```

CLI не отправляет ордеров, не выполняет replay, не меняет Supabase. При403 не
создаёт dataset. В snapshot test_start отделяет warmup. Нельзя выдавать snapshot
за отчёт стратегии или заменять цену Binance его данными вручную.

## Развёртывание и откат

Новых dependencies/SQL нет. Commit можно развернуть с отсутствующим/false flag:
старый market/execution path остаётся прежним. Для отката preview убрать flag
и перезапустить; balances/history/source Auto42 не менялись. Не нужен RESET DEMO.
Программный rollback — parent commit; не удалять таблицы.

Непрерывные SL/TP при закрытом браузере требуют separately verified always-on
server monitor с durable recovery. Render Free + minute cron этому условию не
соответствует. Платные сервисы не подключались. Preview background WS — не
execution monitor и не доказательство автономной торговли.

## Результаты тестов и review

- Полный Python suite: **1145 passed**, 0 failed, 1 Starlette/AnyIO deprecation
  warning, 70.60 s. После уточнения числовых bounds дополнительно прошли все
  18 новых Python tests (в том числе очень большие Decimal exponents).
- Все 12 Node suites: **171 passed**, 0 failed; JS syntax, Python AST и import
  app.main: PASS. Штатный artifact analogs совместим без изменений.
- HTML: 277 уникальных ID, дубликатов нет. Реальный Android browser: NOT RUN.
- Fake WS проверяет resubscribe, reset и отказ delta до нового snapshot. Тест
  REST fallback подтверждает singleflight/rate cap. Heartbeat20s реализован,
  но реальная сессия Bybit WS, реальные паузы/возобновления Render: NOT RUN.
- Code/security review: fixed host/GET allowlist, no account keys, decimal bounds,
  limited response/pages/deadlines, cancellation, default-off flag, UI namespace
  и отказ существующей Auto42 strategy принять Bybit source. Частные write paths
  и credential signatures в новом runtime-коде не обнаружены.
- Числовые bounds защищают от разворачивания Decimal 1E999999999 в гигантскую
  строку. Instrument verification cached5min под lock и выполняется до публичной
  REST quote и WS subscription. Неверный contract не считается Bybit perpetual.
- Риск/SL/TP/strategy/engine/Supabase/Cloudflare не менялись. Legacy Paper и Demo
  integrations не удалены. Нет автоматического Deploy или включения flags.

Изменены существующие app/main.py и static/index.html (только подключение
default-off preview). Новые: app/bybit_linear/{__init__,client,feed,api}.py,
static/bybit_linear.js, scripts/import_bybit_linear_history.py,
tests/test_bybit_linear.py, tests/test_bybit_linear_frontend.cjs и этот отчёт.

```sh
python -m pytest -q
for file in tests/*.cjs; do node "$file" || exit 1; done
node --check static/bybit_linear.js
python -c 'import app.main'
```

Cloud Python suite: PYTHONPATH=/workspace/ecc-audit-deps:$PWD,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, python -B, enable_sandbox_poll() и
pytest.main(['-q','-p','no:cacheprovider','--tb=short']). Production loop неизменён.
Нет frontend build step: существующий frontend — plain HTML/JavaScript.

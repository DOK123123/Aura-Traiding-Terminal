# BingX / Bitget Futures — отдельная диагностика доступности

База: `851ab6734ab6b7ceb3d2beafc2eeb782181acd83`. Это **не миграция**.
Binance Spot, Auto42, scheduler, Supabase, портфели, стратегия, риск и Bybit preview не изменены.
Флаг `AURA_EXCHANGE_DIAGNOSTICS` выключен по умолчанию.

## Официальные источники и идентичность

BingX: [документация swap V2](https://bingx-api.github.io/docs/#/en-us/swapV2/introduce.html).
Официальный опубликованный JS документации проверен 15 октября 2026;
подтверждены пути V2/V3, подписки Last/Mark и GZIP/Ping/Pong.
Контракт **BTC-USDT**, BTC asset, USDT currency, действующий USDT perpetual в swap API.

REST host `https://open-api.bingx.com`:

- GET `/openApi/swap/v2/quote/contracts` — metadata.
- GET `/openApi/swap/v2/quote/ticker?symbol=BTC-USDT` — Last, closeTime.
- GET `/openApi/swap/v2/quote/premiumIndex?symbol=BTC-USDT` — Mark.
- GET `/openApi/swap/v3/quote/klines?symbol=BTC-USDT&interval=15m&limit=5`;
  также `interval=1h`, `4h`.
- WS `wss://open-api-swap.bingx.com/swap-market`;
  `reqType=sub`, `dataType=BTC-USDT@lastPrice` и `BTC-USDT@markPrice`.
  Server `Ping` → client `Pong`, поддержка GZIP.

Bitget: [контракт](https://www.bitget.com/api-doc/contract/market/Get-All-Symbols),
[ticker](https://www.bitget.com/api-doc/contract/market/Get-Ticker),
[свечи](https://www.bitget.com/api-doc/contract/market/Get-Candle-Data),
[WS ticker](https://www.bitget.com/api-doc/contract/websocket/public/Tickers-Channel).
Эти страницы вернули HTTP403 из Codex; это **не ошибка REST API**.
Формат V2 и идентичность дополнительно проверены реальными публичными ответами REST/WS.
Старый официальный GitHub apidoc содержит V1: он не используется как основание для подмены V2.
Контракт **BTCUSDT**, `productType=USDT-FUTURES`, `symbolType=perpetual`,
base BTC / quote USDT / `supportMarginCoins=[USDT]`, status normal.

REST host `https://api.bitget.com`:

- GET `/api/v2/mix/market/contracts`.
- GET `/api/v2/mix/market/ticker` — Last `lastPr`, Mark `markPrice`, timestamp `ts`.
- GET `/api/v2/mix/market/candles` — `granularity=15m`, `1H`, `4H`, `limit=5`.
- У всех запросов фиксированы `symbol=BTCUSDT&productType=USDT-FUTURES`.
- WS `wss://ws.bitget.com/v2/ws/public`;
  `op=subscribe`, args `instType=USDT-FUTURES`, `channel=ticker`, `instId=BTCUSDT`.
  Application heartbeat `ping`/`pong`; отдельно проверяется transport ping/pong.

### Лимиты

BingX опубликованный rate-limit registry указывает 5/s для используемых quote endpoints.
Актуальные численные лимиты **Bitget V2 не удалось независимо перечитать** из-за HTTP403
документации; не используем старые V1 лимиты как проверенные V2.
Наша диагностика существенно ограниченнее: один ручной запуск/120 секунд/process,
одна одновременно выполняющаяся диагностика/process, последовательные REST-запросы
каждой бирже (BingX 6, Bitget 5), не более двух WS попыток с backoff 0.5 секунды.
REST без повторов (максимум одна попытка), без пагинации и full-history.
HTTP429 не повторяется; после restricted/rate-limited contract/ticker/candles дальнейшие
запросы этому провайдеру прекращаются. Межпроцессного distributed limiter нет;
рассчитано на текущий один worker Render, не на кластер.

## Архитектура и безопасность

`app/exchange_diagnostics/probes.py`: закрытый allowlist GET/WS, никаких ключей,
подписей, аккаунтов, ордеров, исполнения стратегии или DB клиентов. Redirects запрещены.
HTTP stream максимум 1MiB, тайм-аут 6s/request; WS max message 64KiB, включая
распакованный GZIP, queue 8, session до 9s, максимум 2 attempts.
Общий бюджет каждой биржи 58s, две биржи параллельно, HTTP client закрывается.
Нет таймера/фонового polling. WS закрывается context manager на успехе, ошибке и отмене.

`api.py`: отдельные owner-only GET `/api/exchange-diagnostics` и
POST `/api/exchange-diagnostics/run`. POST защищён существующим owner HTTPBasic
и `X-Aura-Paper: local-only`/same-origin policy. Этот POST запускает лишь публичные
GET/WS проверки, не выполняет биржевой POST. Нет URL-параметров от пользователя.
Параметры отсутствуют полностью: выбрать произвольный host/endpoint нельзя.
Отчёт только в памяти до рестарта. Логи: лишь название биржи и статусы, без raw response,
headers или исключений. API code возвращается только коротким числовым значением.

Bybit **не меняется**: читается исключительно существующий in-memory WS preview.
Новые Bybit REST/WS запросы сравнением не запускаются. Если preview flag выключен,
`NOT_TESTED`; REST `NOT_TESTED`, даже если существующий WS LIVE.

Проверки: точная contract identity, конечные положительные цены, timestamp ms,
30s freshness ticker / 3s future tolerance; aligned UTC OHLCV, отсутствие duplicate/gap,
порядок ascending или descending, исключение незакрытой свечи и проверка последнего
ожидаемого закрытого интервала. Это проверка маленького recent window, не всей истории.

**BingX REST Mark `updateTime` оказался старым**. Он не подменяется временем загрузки:
цена сохраняется для диагностики с `mark_freshness=UNVERIFIED`, REST aggregate
`PARTIALLY_AVAILABLE`. WS Mark имеет отдельный event timestamp и проверяется независимо.
HTTP200 с API error не считается успехом. Отдельные DNS/TLS ошибки распознаются по
типу цепочки исключений; при отсутствии такой информации остаётся NETWORK_ERROR,
а не выдуманная причина. Для пропуска Mark — PARTIALLY_AVAILABLE, не AVAILABLE.

Результат — **исторический снимок диагностики**, не постоянно текущая цена и не
разрешение торговать. UI постоянно поясняет это; цены не передаются в market pipeline.
В деталях доступны timestamps, latency, HTTP/API codes и отдельные состояния свечей.

## Фактически проверено из Codex, не из Render

Воспроизводимый разовый результат: `docs/EXCHANGE_CONNECTIVITY_CODEX.json`.
Команда из корня: `python -m scripts.check_exchange_connectivity`.
Нужны существующие зависимости requirements.txt, без account credentials.

| Биржа | REST | Свечи 15m/1h/4h | WS Last+Mark | Вывод |
|---|---|---|---|---|
| BingX | PARTIALLY_AVAILABLE | AVAILABLE / AVAILABLE / AVAILABLE | AVAILABLE, transport pong | Mark REST freshness не доказана |
| Bitget | AVAILABLE | AVAILABLE / AVAILABLE / AVAILABLE | AVAILABLE, transport и application pong | Разовый тест успешен |
| Bybit | NOT_TESTED в этом прогоне | NOT_TESTED | NOT_TESTED | Только существующий preview на Render |

В обоих real WS тестах первая попытка успешна. **Реальное восстановление после
разрыва не спровоцировано**, reconnect policy проверена offline mock-тестом.
У BingX application Ping не пришёл за короткую сессию: `application_heartbeat=false`
не выдаётся за проверенный heartbeat, transport pong подтверждён.
Это не доказательство круглосуточной надёжности или разрешённости подключения с Render.
В рамках задачи не выполнялись authenticated Render тест, deploy или Android browser test.

## Как проверить на Render с Android

1. Развернуть этот commit обычным Deploy latest commit (автоматический deploy здесь не запускался).
2. Render → Aura service → Environment → добавить **`AURA_EXCHANGE_DIAGNOSTICS=true`**.
   Сохранить с redeploy. Ключи BingX/Bitget не нужны.
   Существующий `AURA_TESTNET_VIEW_PASSWORD` не менять.
3. Открыть https://aura-traiding-terminal.onrender.com, найти
   **Exchange Connectivity Diagnostics**, войти владельцем через ссылку `aura`.
4. Нажать **Run connectivity test**, дождаться до 60s. За это время кнопка блокируется.
5. Раскрыть детали BingX/Bitget: contract, HTTP/API status, Last/Mark, свежесть,
   свечи 15m/1h/4h, latency и WS. Именно этот отчёт выполняется на Render.
6. Для Bybit сравнение возможно, если уже включён существующий preview;
   менять его настройку ради BingX/Bitget необязательно. Disabled означает NOT_TESTED.
7. Повторить не ранее 120 секунд. Зафиксировать несколько тестов в разное время;
   единичный успех не доказывает устойчивость. Затем можно выключить диагностический флаг.

**Не нажимать START PAPER**, не менять источники/балансы. Проверить на Android
320–430px раскрытие деталей, доступность кнопки, отсутствие горизонтальной прокрутки,
возврат кнопки после timeout/401. Автоматизированного real mobile test не выполнялось.

## Проверки и review

См. результаты в итоговом отчёте commit. Добавлены offline unit/API/WS тесты,
включая отключённый feature flag, auth/CSRF, concurrent/cooldown, ошибочные данные,
HTTP403/451, HTTP200 API error, timeout/DNS/TLS, stale timestamps, malformed JSON,
Mark missing, GZIP bounds и закрытие WS при disconnect.

Применены локальные ECC guidance security-review/fastapi-patterns как отдельные
ручные review passes, без запуска внешних ECC agents/plugin. Architecture review:
новый isolated модуль, в main лишь wiring; нет imports execution/private clients.
Security review: fixed allowlist, redirects off, bounded resources, owner/CSRF,
no raw upstream errors, no credential variables. Обнаруженная при review ошибка:
missing Mark мог перезаписать BLOCKED_451 → PARTIALLY_AVAILABLE; исправлено,
добавлен regression test. Trading-math review: финансовые расчёты не затронуты,
цены Decimal, OHLCV проверяются, стратегии/история/источники неизменны.

### Фактический результат проверок

- Полный Python suite: **1161 passed**, 1 предупреждение deprecation Starlette/AnyIO,
  69.75s. После финального уточнения WS HTTP429 / UI comparison повторно выполнены
  все 16 новых Python tests: **16 passed**, и 3 новых JS tests: **3 passed**.
- Все 13 Node suites: **174 passed**. Python AST всех app/scripts/tests,
  import `app.main`, `node --check` нового JS: PASS.
- Pattern-based static credential scan изменяемых файлов: совпадений нет.
  Это эвристический scan, не утверждение о полном выявлении всех возможных секретов.
- Exchange network path review: единственный HTTP transport — `client.stream('GET', …)`;
  WS сообщения только public subscribe/ping/pong. Декоратор собственного POST `/run`
  не является exchange write. DB/portfolio dependencies отсутствуют.
- Сравнение локальных Git blob hashes с tree main: изменены только существующие
  `app/main.py` (три wiring строки) и `static/index.html` (новая панель/assets);
  все остальные изменения — отдельные новые файлы. Существующий Bybit модуль,
  Auto42, balances, DB schema, execution/risk и scheduler не изменены.
- Браузер/Android/реальный Render owner diagnostic: **NOT RUN**.
- Дополнительные ruff/mypy/bandit не запускались; build не нужен (plain JS).

Команды проверок: `python -m pytest -q` (в данной sandbox — существующий
`enable_sandbox_poll()` из scripts/replay_aura_csv, только в тестовом launcher,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-p no:cacheprovider`),
`node tests/test_exchange_diagnostics_frontend.cjs` и все остальные `tests/*.cjs`.
В тестовой среде существующие pinned packages доступны через
`PYTHONPATH=/workspace/ecc-audit-deps:$PWD`; зависимости проекта не изменены.

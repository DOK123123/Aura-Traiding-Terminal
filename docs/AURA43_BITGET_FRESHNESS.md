# Aura 4.3: Bitget freshness и saved_mode

Основа: main `a6a8500`, PR #28 объединён. Production-настройки, PAPER, баланс,
позиции, SQL и секреты этой работой не меняются.

## Точный источник сообщения

`app/active43/bitget.py: Client.fresh_time()` выбрасывает
UPSTREAM_CLOCK_OR_STALE_RESPONSE, если:

`not (-3000 <= Render_time_ms - Bitget_timestamp_ms <= 10000)`.

Ошибка отображается в `static/active43.js` как «Часы Bitget или ответ не прошли
проверку свежести». Проверяются отдельно:

- requestTime каждого успешного публичного ответа;
- data.serverTime `/api/v2/public/time`;
- ticker data[0].ts для BTCUSDT USDT-M Futures;
- возраст котировки в конце market diagnostics.

Возраст >10000 ms означает старый timestamp относительно Render; возраст <-3000
ms — timestamp в будущем. Сам знак/величина не доказывают причину: это могут быть
часы хоста/провайдера, устаревший ответ/cache, сетевое ожидание или задержка внутри
диагностики. Код не сдвигает часы и не компенсирует offset, чтобы принять ответ.

## Воспроизводимый дефект и исправление

В main market_probe сначала получал quote, затем specs и три последовательных
набора свечей, и лишь затем повторно проверял возраст первой котировки.
Тест с 4 s задержки на каждый candle request давал ERROR
UPSTREAM_CLOCK_OR_STALE_RESPONSE с age_ms=12000. Все ответы приходили свежими,
но сама диагностика состарила котировку перед показом.

Теперь market_probe сначала проверяет закрытые свечи, затем получает quote и
проверяет Futures specs и окончательную свежесть. Instrument cache означает,
что specs после quote не добавляет сетевого запроса. Количество запросов не
увеличилось. Все отдельные timestamp-проверки, диапазон -3/+10 s и общий бюджет
24 s остаются прежними. При действительно устаревшем ticker.ts диагностика ERROR;
при clock drift ERROR; при переходе границы свечи проверка last_closed_at остаётся.
Это исправление порядка read-only диагностики, не стратегия и не разрешение входа.

Дефект воспроизведён на исходном main и защищён регрессией. Причина **конкретных
production** ошибок пока не установлена: отсутствуют логи соответствующего
timestamp и доступ к часам/запросам процесса Render. Исправление не обещает убрать
легитимные отказы Bitget при stale/cached/slow ответах.

## Безопасная диагностика в Render

Logger `app.active43.bitget` пишет JSON с component=ACTIVE43_BITGET_PUBLIC:

- FRESHNESS_REJECTED: code, check (requestTime/serverTime/ticker.ts/diagnostic_quote.ts),
  фиксированный path, render_at_ms, upstream_at_ms, age_ms, границы проверки,
  attempt и request_elapsed_ms (для requestTime).
- REQUEST_RETRY / REQUEST_FAILED: code, фиксированный path, attempt, http_status.

request_elapsed_ms измеряется monotonic на одной попытке от начала HTTP до
завершения чтения тела. Это не измерение NTP offset. Публичные exchange timestamps
и пути не содержат учётных данных. Headers, query, response body и exception text
не выводятся. В owner/scheduler diagnostics JSON поле bitget.freshness добавляется
при доступной подробности MarketError. Risk/strategy journal продолжает получать
прежний безопасный code, не подробности исключения. Cloudflare контракт совместим:
дополнительное поле необязательно, code/status и safety identity не изменены.

Если ошибка приходит через Market.specs(), он сохраняет только прежний error code;
исходный подробный FRESHNESS_REJECTED остаётся в Render logs. Это не повод считать
отсутствие вложенного freshness доказательством исправных часов.

## Свечи и повторы

Candle timestamps — миллисекунды UTC начала интервала, кратные шагу 15m/1h/4h.
endTime передаётся ровно на границе, она исключается API. Проверяются сортировка,
дубликаты, пропуски, OHLCV, forming bars и конечная закрытая граница. Правила не
менялись, будущие свечи не используются.

Bitget GET 502 уже повторялся максимум один раз через 250 ms внутри 12 s бюджета
(HTTP timeout 5 s); повторный ответ заново проходит freshness. Остаточный 502 даёт
HTTP_ERROR, network timeout — UPSTREAM_TIMEOUT. Rate-limit/cooldown и host/GET
allowlist остаются. Новые тесты подтверждают 502→fresh, 502→stale, 502→502 и
502→timeout; нет fallback на Spot, старую котировку или другой источник.

Не путать две разные ошибки:

| Hop | Где видеть |
| --- | --- |
| Cloudflare → Render HTTP 502 | Worker RENDER_REACHED/REQUEST_FAILED с http_status=502, его bounded retry/cold-start delay |
| Render → публичный Bitget HTTP 502 | Render ACTIVE43_BITGET_PUBLIC REQUEST_RETRY/FAILED, path `/api/v2/…`, http_status=502 |

При PAPER ON ошибка источника блокирует вход, сохраняет PAUSED, не обновляет
last_successful_run_at как успешный рынок и не создаёт позицию. Это проверено только
в изолированных тестах. При PAPER OFF/saved_mode пустой счёт сохраняет heartbeat
без получения данных Bitget. Поэтому Scheduler ACTIVE одновременно с Bitget ERROR
в market diagnostics — допустимое состояние, а не доказательство торговли.
Тест проверяет реальный scheduler HTTP /tick и валидирует его ответ через Worker
saved_mode, повтор не создаёт второй TICK. Production tick в задаче не запускался.

## Реальные наблюдения и недостающие данные

Однократный публичный Client.quote() из рабочей среды прошёл все проверки:
BTCUSDT / BITGET / USDT_PERPETUAL / USDT-FUTURES, age ticker около 79 ms на момент
вывода. Это LOCAL_PUBLIC_BITGET_NOT_RENDER — не подтверждение доступности/часов
Bitget с Render и не production paper cycle.

Для установления production-причины нужны события Render **за время ошибки**:
FRESHNESS_REJECTED (check/path/render_at_ms/upstream_at_ms/age_ms/request_elapsed_ms),
соседние REQUEST_RETRY/FAILED (attempt/http_status), время диагноза и соответствующий
Worker REQUEST_FAILED с phase/http_status, если он был. Если есть подозрение на часы,
нужны измерения UTC/NTP на Render в этот момент. Не нужны секреты, raw HTTP headers,
ключи Supabase или тела торговых ответов. Одна надпись в UI не различает эти причины.

После owner Merge и Render Deploy искать ACTIVE43_BITGET_PUBLIC в Render Logs и
нажать существующую read-only «ПРОВЕРИТЬ ВСЮ СИСТЕМУ». Оставить PAPER OFF и
saved_mode без изменений. Новые env, SQL, ключи и Cloudflare deploy не нужны.

## Review и границы

Code review: freshness inequality, closed-candle selection, retries и trading
thresholds не менялись. Перенос только в диагностике. Реальные отказы по свежести
не превращаются в CONNECTED. Security review: только публичные Bitget GET,
фиксированные paths и безопасные поля в логах, никакого нового API/доступа к счетам.
Критических/high замечаний не обнаружено. Aura 4.2 и Practice не менялись.
Merge/Deploy, START/STOP/RESET/initialize, production tick и реальные ордера
не выполнялись. Production-причина и production-результат исправления NOT VERIFIED.

## Результаты ветки

Полный Python suite с `AURA_ACTIVE43_VERIFY_POSTGRES=true`: **1581 passed,
2 skipped**, 207,73 s. Пропуски — существующие standalone Auto42/Practice PostgreSQL
opt-in; Active43 реальный PostgreSQL выполнен. Полный Node suite: **236 passed**.
Адресные Bitget/diagnostics/Worker contract проверки: **75 passed**. В добавленных
тестах — 19 freshness/source-failure сценариев и один saved_mode server→Worker.
Проверены точные границы времени, stale request/server/ticker, network timeout,
502 retry, отсутствие OPEN на ошибке и неизменность тестового баланса, duplicate OFF.
AST 232 Python-файла, import app.main и diff --check: PASS.
Одно существующее Starlette/anyio deprecation warning.

# AURA LIVE MANUAL TRADER 5.0 — проверка выпуска

Исторический отчёт первой итерации на `1f8975b`. Новая проверка профилей,
WAIT, нескольких периодов и режимов: [profiles/REPORT_RU.md](profiles/REPORT_RU.md).

Проверялось локально 28 октября 2026. Production, PAPER, Render, Supabase,
Cloudflare и main не менялись. Active43 и Practice код/настройки не изменены.

| Проверка | Результат | Доказательство |
|---|---|---|
| Публичный Bitget REST пяти таймфреймов | PASS из среды разработки | PUBLIC_NETWORK_CHECK.json: HTTP 200, code 00000, 201 строк на frame |
| Публичный Bitget WS Futures | PASS из среды разработки | 40 реальных сообщений ticker + все 5 candle channels, 500 строк initial snapshot, hash capture |
| LIVE формирующаяся свеча и цена | PASS offline integration | Browser actual Hub, изменение текущей свечи и ticker без reload |
| Desktop / mobile touch | PASS эмуляция | BROWSER_CHECK.json и screenshots, реальный Chromium, touch drawing |
| Android Chrome на физическом устройстве | NOT TESTED | Нужен отдельный короткий smoke-test владельца после разрешённой публикации |
| Owner / CSRF / stale / risk / double-click / restart | PASS offline | Python/JS tests, loopback Uvicorn, отдельная SQLite |
| LONG/SHORT, ручной CLOSE, SL/TP, fees/slippage | PASS offline | Независимые численные ожидания, idempotency/restart cases |
| PostgreSQL / RLS / CAS / atomicity | PASS disposable local PostgreSQL | tests/test_manual_paper_postgres.py — 2 passed, 10 SQL checks, network=none |
| Production новая версия / реальная ручная сделка | NOT TESTED | Не публиковалась, никаких рабочих сделок не создавалось |
| Подтверждённая прибыльность | INSUFFICIENT_EVIDENCE | Нет независимого OOS и достаточных реальных сигналов |

## Историческая проверка LIVE против closed-only

Реальные официальные Bitget minute ZIP, SHA-256 каждого входа в replay/summary.json.
Исходные архивы June–September 2026, их UTC timestamps не сдвигались: месячные
имена имеют UTC+8 границу. Непрерывная последовательность без дубликатов и
пропусков; для 200 закрытых 4h свечей используется прогрев до начала оценки.
Источник только BTCUSDT USDT-M Futures. Реестр #59 уже помечает этот календарь
просмотренным. **REUSED EXPLORATORY DATA, не независимый OOS.**

Период оценки: 2026-09-23T00:00:00Z — 2026-09-30T00:00:00Z exclusive.
10 080 последовательных минутных наблюдений. В каждом состоянии видны только
завершённые прошлые минуты и текущая цена open с предполагаемой доступностью
через 1 секунду. Будущие high/low/close/volume текущей минуты не попадают в
аналитику. 5m/15m/1h/4h формируются из доступного префикса. Сравнение с точной
неизменённой Python closed-only `assess`, а не её приблизительным переводом.

| Модель | Наблюдений LONG / SHORT | Сделок | Net PnL | Cost stress ×1,5 / ×2 |
|---|---:|---:|---:|---|
| LIVE preliminary | 0 / 0 | 0 | 0 USDT | 0 сделок / 0 сделок |
| Closed-only | 0 / 0 | 0 | 0 USDT | 0 сделок / 0 сделок |

Ожидание/PF/Win Rate не определены при нуле сделок. Нулевая просадка здесь
означает отсутствие экспозиции. Исчезновение реальных предварительных сигналов
в этом периоде оценить нельзя: ни одного не было. Синтетический регрессионный
тест отдельно доказывает, что LONG может перейти в WAIT без изменения закрытого
контекста. Никакого изменения порогов после просмотра результата не выполнялось.

Причины WAIT в LIVE:

- `CLOSED_TREND_NOT_ALIGNED`: 6805.
- `NO_LIVE_ENTRY_CONFLUENCE`: 551.
- `LIVE_MOMENTUM_NOT_CONFIRMED`: 403.
- `CONFLICTING_4H`: 2300.
- `PROVISIONAL_CANDLE_NOT_CONFIRMED`: 12.
- `PARTIAL_VOLUME_NOT_SUPPORTING`: 3.
- `NO_PAST_ORDERED_SWING`: 6.

Ограничения replay: это минутный proxy, не полноценный исторический bid/ask/event
stream. Внутриминутные последовательности и историческая задержка публикации
неизвестны. Предположения spread 2 bps, fee 10 bps и slippage 5 bps/сторону;
исполнение отложено до первого минутного open не ранее чем через 60 секунд,
проверяются зона, размеры, риск, дневной бюджет, просадка и одна позиция.
После ручного принятия плана модель задержанного исполнения не воспроизводит
его браузерный 2-секундный TTL; это отдельная иллюстративная модель для сравнения,
не доказательство достижимого LIVE fill. Open не гарантированная цена сделки.
Funding и глубина книги отсутствуют. Гэпы неблагоприятны, SL-first при dual touch,
zero-volume не исполняет вход/SL/TP, terminal close — явная оценка.
Исследовательский simulator float; основной Manual Paper ledger — Decimal и
проверен отдельными независимыми известными ответами.

Для выводов о качестве сигналов нужен будущий read-only event replay с сохранением
bid/ask/receipt timestamps и замороженным кодом. Его сбор/расписание не включались.

## Результаты regression

Обычный локальный full Python: 2031 passed / 4 skipped до добавления четырёх
отдельно прошедших replay reference-тестов. Эти четыре skips — opt-in PostgreSQL,
не считаются PASS. Отдельный Manual PostgreSQL — 2 passed. Финальный full прогон
со всеми четырьмя PostgreSQL flags и GitHub CI фиксируется в описании PR.
JavaScript: 296 passed, 0 skipped. Новый LIVE suite — 12 passed.
AST, import app.main, node --check и git diff --check — PASS.
Единственный Python warning — существующая Starlette/anyio deprecation.

## Ограничения и следующий безопасный шаг

- Ни production connectivity Render, ни production Supabase Manual Paper не проверены.
- Исходный Active43 PAPER остаётся вне полномочий нового модуля; его фактическое
  production ON/OFF не запрашивалось и не заявляется подтверждённым.
- Физический Android не доступен. Эмуляция не заменяет его проверку.
- Free Render sleep задерживает защитные exits; непрерывная защита 24/7 не обещана.
- Результаты и UI не утверждают, что LIVE или closed Analyst прибыльны.
- Глубина live-истории фиксирована 201, включённые большие архивы не нужны браузеру.
- История рекомендаций ограничена 100 событиями текущей вкладки; исполненные
  виртуальные сделки имеют отдельное постоянное хранилище.

Следующее действие — review Draft PR и SQL/env runbook. Merge, миграции, deploy,
включение ручного счёта и любые production сделки требуют отдельного разрешения.

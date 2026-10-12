# Aura Auto Paper: независимая диагностика

Дата подготовки: 2026-10-12 UTC.

## Результат

Проверенный архив BTCUSDT 15m за последние 30 полных UTC-дней в рабочем
каталоге отсутствует. Ранее публичный запрос истории был прерван; в текущем
проходе сетевое получение свечей не выполнялось. Поэтому ниже намеренно нет
чисел сигналов, входов, закрытых сделок, PnL или просадки. `0` здесь не означает
отсутствие сигналов: результат является `NO_HISTORY`, а не нулевым прогоном.

Для даты окончания 2026-10-12 ожидаемый диапазон `[2026-09-12 00:00,
2026-10-12 00:00) UTC` содержит 2880 закрытых свечей. Это ожидаемое число, а
не наблюденное число.

| Метрика реального BTCUSDT / 15m за период | Результат |
| --- | --- |
| Ожидаемые закрытые свечи | 2880 |
| Фактически проверенные свечи периода | Неизвестно: NO_HISTORY |
| Потенциальные направления / подтверждённые LONG и SHORT | Не вычислено |
| Отказы по каждому фильтру и причине Auto | Не вычислено |
| Допустимые входы / выходы / закрытые сделки | Не вычислено |
| Комиссии, realized PnL, equity, максимальная просадка | Не вычислено |
| Первые пять сигналов | Не вычислено |

Offline fixtures ниже проверяют поведение кода, а не частоту сигналов или
доходность BTCUSDT. В live audit хранится только 2000 решений / 30 дней,
последние 100 возвращаются API; эти пределы не позволяют считать всю
2880-свечную историю по одной выдаче API.

Скрипт запускается отдельно и не использует Strategy Lab, production SQLite,
credentials или private exchange clients:

```bash
python scripts/diagnose_aura_auto.py \
  --end-date 2026-10-12 \
  --snapshot /path/to/immutable-btcusdt-15m.json \
  --output /tmp/aura-auto-diagnostic.json
```

Снимок должен содержать `symbol`, `timeframe`, `source = Binance · Spot` и
закрытые numeric OHLCV. Скрипт требует 10 000 свечей прогрева по умолчанию,
проверяет непрерывность и не заполняет пропуски. Для получения публичного
снимка предусмотрен явный `--fetch --snapshot ...`; это единственный сетевой
режим, он не принимает credentials, не следует редиректам и ограничен размером
и временем. Результат нельзя перезаписать.

Пример безопасной проверки отсутствия истории:

```bash
python scripts/diagnose_aura_auto.py --end-date 2026-10-12 \
  --output /tmp/aura-auto-no-history.json
```

Он возвращает `NO_HISTORY` и оставляет метрики `null`.

## Подтверждённый путь и причина отсутствия сделок

Production-путь: `Market.window()` проверяет закрытый непрерывный OHLCV-window и
свежесть → `Service.auto_tick()` сначала выполняет защитные виртуальные выходы →
`Auto.needs_signal()` проверяет новый watermark/source/TF → `SignalReader.read()`
отбрасывает данные после текущей свечи и вызывает неизменённый
`patterns.engine.evaluate(..., PatternConfig(), context=500)` → создаёт `Signal`
→ `Auto.process()` проверяет source/timeframe, открытую позицию, SL/TP policy и
риск → `Engine._open_in_transaction()` создаёт только локальную paper-позицию.

`NO_SIGNAL` означает успешное вычисление, после которого
`patterns.signals.decide()` вернул `signal='WAIT'`. Это отличается от
`SIGNAL_UNAVAILABLE`, который означает timeout, ошибку истории, снимка или
вычисления. Направленная сторона без SL/TP при политике `SKIP` получает
`STOPS_UNAVAILABLE`; при `PAPER_SETTINGS` используются только paper SL/TP 2%/4%.
Другие блокировки: `POSITION_ALREADY_OPEN`, `STALE_DATA`, `MARKET_GAP`,
`SOURCE_MISMATCH` и `SNAPSHOT_MISMATCH`.

Historical Pattern возвращает `WAIT`, пока одновременно не выполнены условия:
минимум 20 совпадений, similarity от 75 при отборе аналогов, directional rate от
60%, Wilson lower bound выше 50%, неокруглённый confidence от 40, ожидаемое
направленное движение выше 5 bps и положительная направленная median на горизонте
20 свечей. Как минимум на половине горизонтов (5/10/20/50) направленные
average и median должны быть положительными. MTF влияет на confidence, но
не является отдельным обязательным подтверждением; его отсутствие нейтрально.
Пороги и формулы не менялись. Поэтому `NO_SIGNAL` не доказывает ошибку получения
свечей. Предупреждения о близости high/low и объёме сами по себе не запрещают вход.

Минимум 500 свечей позволяет выполнить расчёт, но не гарантирует аналоги: до
570 свечей нет даже одного допустимого кандидата. При lookback 20, максимальном
горизонте 50 и исключении перекрытий для 20 аналогов нужно как минимум 1900
свечей (около 19.8 дня на 15m); similarity-фильтр может потребовать больше.
История production обычно запрашивается по 10000 свечей и расширяется архивом.
Количество истории на конкретном Render-инстансе здесь не проверено.

Обычная строка `NO_SIGNAL`/`SKIPPED` содержит `signal_result=WAIT` и confidence;
`signal_result=null` означает, что на этой свече сигнал не вычислялся.
Успешный вход в `_record()` передаёт технический аргумент `NO_SIGNAL`, но при
наличии trade сохраняет `action=OPENED`, `trade_opened=true` и
`rejection_reason=null`: это не ложный отказ. Дубликаты/cooldown не вызывают
повторный расчёт, OFF и baseline записывают свои причины.

## Воспроизведённый дефект интеграции: новый close и кэш истории

`HistoryService.get()` возвращает кэш моложе 60 секунд без проверки наличия
новой закрытой свечи. Если chart/Paper window уже содержит новый close, а
история ещё из кэша предыдущей свечи, production `SignalReader` выдаёт
`SNAPSHOT_MISMATCH`, не WAIT. Offline-тест с действующими Service, SignalReader
и Auto воспроизводит этот путь: `last_signal=null`, записи NO_SIGNAL нет,
но общий `Auto.fail()` продвигает watermark, и та же свеча больше не вычисляется.
Исправление только SIGNAL_UNAVAILABLE не распространяется на этот код ошибки.
Это подтверждённый дефект обработки несогласованного снимка (средняя серьёзность),
а его возникновение на конкретном Render-инстансе пока не подтверждено.
Runtime здесь не исправлялся: безопасный отдельный шаг — синхронизировать
history cache с требуемым close и не расходовать свечу при временном mismatch,
с ограниченным retry и неизменными защитами. Не следует лечить это снижением
порогов стратегии.

Историческая панель позволяет собственные config/context (500/2000), а Auto
всегда использует `PatternConfig()` и context=500. Поэтому сигнал панели
при изменённых настройках не равен сигналу Auto; сравнение требует одинаковых
defaults, закрытой свечи, source и архива. Это существующая семантика, не новая
оптимизация и не доказанный дефект.

## Что можно и нельзя заключить о Render

Подтверждено по коду и offline-тестам: для настоящего `NO_SIGNAL` стратегия
посчитана, но вернула WAIT; риск и SL/TP при WAIT ещё не проверяются. При
подтверждённом LONG/SHORT политика SKIP заблокирует вход, поскольку SignalReader
не выдаёт уровни SL/TP. Bybit/Binance account integration не участвует в Auto
Paper и её HTTP 403/451 не является самостоятельным препятствием.

Не подтверждено: текущая сохранённая политика, журнал, размер архива, реальное
распределение confidence/аналогов и версия приложения на Render. Доступа к
аккаунту, credentials и live-журналу не было. Возможные причины отсутствия сделок
на конкретном инстансе — WAIT по одному из порогов, SKIP, PAUSED после restart/
исчерпания retry, несовпадение источника или неполная история. Это гипотезы,
пока не сопоставлены с его фактическими записями.

Стандартные настройки 10000 USDT / 1% / 2000 USDT / одна позиция не запрещают
вход сами по себе: размер ограничивается минимумом риск-бюджета, номинала и
свободного баланса. При условной цене 100 USDT, SL 2%, TP 4%, комиссии 0.1%
quantity равна 20; fee-inclusive риск LONG 43.96, SHORT 44.04 USDT, ниже
бюджета 100 USDT. Это арифметический пример, не результат реальной торговли.

Следующий безопасный шаг: прочитать существующий защищённый
`GET /api/paper/state?scope=AUTO` и соответствующий Historical Pattern analysis
для той же закрытой свечи/источника. Сопоставить `status`, `fallback_policy`,
`last_processed_candle`, `signal_result`, confidence и число аналогов/риски.
Затем получить достоверный неизменяемый snapshot для воспроизводимого replay.
Без этих данных нет доказанного основания менять стратегию или её пороги.

Дефект `SIGNAL_UNAVAILABLE` исправлен commit
`a6e422dd6eb7012dd7afffb3ca273aef9d338c91`: watermark не продвигается, retry
сохраняется в SQLite, повтор идёт через 15/30 секунд, после трёх ошибок состояние
становится `PAUSED/SIGNAL_RETRY_EXHAUSTED`. Это исправляет потерю свечи, но не
превращает `WAIT` в сделку.

## Что именно воспроизводится

Replay создаёт временный SQLite и вызывает production-путь в том же порядке:
закрытая свеча → `Market` → `Engine.advance` (защитные выходы) →
`SignalReader` → неизменённый `patterns.engine.evaluate` → `Auto.process`.
Используются явно заданные диагностические defaults `Settings`: starting balance 10000 USDT, fee 0.10%
на сторону, risk 1%, maximum position notional 2000 USDT, максимум одна
одновременная позиция и fallback `PAPER_SETTINGS` (SL 2%, TP 4%).

SignalReader отбрасывает будущие/формирующие свечи до расчёта признаков. Скрипт
записывает направления сигналов, входы, причины отказов, первые пять сигналов,
закрытые сделки, комиссии, Decimal-PnL, equity curve и SHA256 исходного снимка
и production-кода. PnL независимо сверяется по формуле `gross - entry fee -
exit fee`; для SHORT знак инвертируется.

## Проверка live Auto Paper после baseline

Offline regression tests подтверждают, что следующая новая закрытая свеча после
`ACTIVATION_BASELINE` читается и может открыть одну paper-позицию, а повтор того
же REST/WebSocket snapshot не открывает вторую позицию. После restart состояние
остаётся `PAUSED` и требует явного Resume.

Обнаруженное ограничение production-семантики сохранено: если между тиками
прошли несколько свечей, промежуточные свечи получают `MISSED_CANDLE_NO_ENTRY`,
а сигнал читается только для последней свечи. При серии ошибок применяется
ограниченный retry; промежуточные свечи после появления новой связной свечи
получают `MISSED_CANDLE_NO_ENTRY`, без backfill-входа.

## Тесты

Добавлены `tests/test_aura_auto_diagnostic.py` (**22 теста**): в том числе календарь и
forming-candle exclusion, duplicate/gap/order validation, отсутствие фиктивного
PnL, LONG/SHORT fee-inclusive accounting, baseline/restart, duplicate execution,
missing ticks и signal failure watermark.

Проверено:

- полный Python suite текущей диагностики: **657 passed**, 1 существующее
  предупреждение Starlette/httpx;
- retry-тесты Auto Paper: **11 passed**;
- diagnostic и retry в полном наборе: **22 + 11 = 33 passed**;
- JavaScript: paper 57, reliability 9, Bybit 13, Binance Testnet 11,
  Strategy Lab 11 — всего **101 passed**;
- static scan: credentials PASS, exchange-write/private-client scan PASS,
  Python syntax/imports PASS (70 files), JavaScript syntax PASS, mobile HTML/CSS
  structural checks PASS;
- полноценный browser/Android/Render прогон не выполнялся.

Команды проверки из корня репозитория: `python -m pytest -q`,
`node tests/test_paper_frontend.cjs`, `node tests/test_frontend_reliability.cjs`,
`node tests/test_testnet_frontend.cjs`, `node tests/test_bybit_demo_frontend.cjs`,
`node tests/test_lab_frontend.cjs`. В этой Cloud-среде pytest запущен через
`/tmp/run-aura-tests.py` с `/tmp/aura-test-deps` в PYTHONPATH и временным
`PAPER_DB_PATH`: только тестовый event-loop workaround, без runtime-изменений.
Доступные версии: FastAPI 0.141.1, uvicorn 0.52.1, httpx 0.28.1,
websockets 16.0, numpy 2.3.5; точное окружение requirements.txt не воспроизводилось.

Диагностические файлы: `scripts/diagnose_aura_auto.py`,
`tests/test_aura_auto_diagnostic.py`, этот отчёт. Runtime strategy, API,
настройки Auto Paper, Binance/Bybit integrations и production storage не
изменялись.

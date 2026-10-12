# Historical Pattern: 30 и 90 дней BTCUSDT / 15m

Дата проверки: 2026-10-12 UTC. Production revision до этого диагностического
commit: `3983404db5f7c63a0d1c59881b92e859764b8a38`.

## Фактический результат

**Бэктест на реальной истории НЕ ВЫПОЛНЕН.** Локального проверенного архива нет.
Короткий GET официального публичного endpoint Binance из процесса Cloud дал
`ConnectError` до получения HTTP-ответа. Проверка с дополнительным сетевым
разрешением была прервана пользователем; её результат неизвестен. Повторных
попыток после прерывания не было. Это не подтверждает HTTP 451/403 Binance и не
доказывает глобальную недоступность источника.

Фактически запущено из корня репозитория:

```bash
python -B scripts/backtest_aura_history.py --end-date 2026-10-12 \
  --output /tmp/aura-backtest-30-90-final-no-history.json
```

Результат: `30d=NO_HISTORY 90d=NO_HISTORY`, exit code 2,
`actual_backtest_performed=false`. Неизвестные результаты остаются `null`.

| Период | Диапазон свечей UTC, конец исключён | Ожидаемые свечи | Фактические метрики |
| --- | --- | ---: | --- |
| 30 дней | 2026-09-12 — 2026-10-12 | 2880 | Не вычислены |
| 90 дней | 2026-07-14 — 2026-10-12 | 8640 | Не вычислены |

LONG/SHORT, отказы, число сделок, комиссии, win rate, PnL, drawdown и profit factor
для обоих периодов неизвестны. Нулевые значения из unit-тестов не заменяют эти
данные. Помесячная доходность также не вычислялась.

| UTC месяц по открытию свечи | Ожидаемо в 30 днях | Ожидаемо в 90 днях |
| --- | ---: | ---: |
| 2026-07 (с 14-го) | — | 1728 |
| 2026-08 | — | 2976 |
| 2026-09 | 1824 | 2880 |
| 2026-10 (до 12-го) | 1056 | 1056 |

Эти числа являются календарным расчётом полноты, а не наблюдениями рынка.

## Воспроизводимый запуск при доступной истории

Для явного публичного GET без ключей, редиректов и сетевого retry:

```bash
python scripts/backtest_aura_history.py --end-date 2026-10-12 \
  --fetch-dir /tmp/aura-real-snapshots-new \
  --max-seconds 3600 --output /tmp/aura-real-30-90.json
```

Каталог и файл результата должны быть новыми. Сначала скачивается и проверяется
30-дневный snapshot, выполняется replay; только после успешного завершения
расширение до 90 дней. При сбое/превышении CPU-бюджета первый результат
`INCOMPLETE`, второй `NOT_RUN`. Длительный replay нужно запускать отдельно от
Render web worker. `--periods 30` выполняет только первый этап.

Офлайн с заранее полученным полным 90-дневным snapshot и прогревом:

```bash
python scripts/backtest_aura_history.py --end-date 2026-10-12 \
  --snapshot /path/to/BTCUSDT-15m-90d-with-warmup.json \
  --max-seconds 3600 --output /tmp/aura-offline-30-90.json
```

Формат snapshot: `symbol=BTCUSDT`, `timeframe=15m`, `source=Binance · Spot`,
`candles` с integer `time` в UTC-секундах и numeric open/high/low/close/volume.
Фиксированный официальный источник:
`https://data-api.binance.vision/api/v3/klines`. По умолчанию ровно 10000 свечей
прогрева **до** каждого периода, затем 2880/8640 свечей оценки. Для 90 дней это
18640 баров. Проверяются UTC-выравнивание, порядок, дубли, пробелы, OHLCV и полное
покрытие; заполнения или молчаливого усечения нет. Формирующие/более поздние
свечи исключаются до расчёта. SHA256 полного и выбранного snapshot фиксируются.
Самостоятельно переданный JSON имеет заявленное происхождение; его Binance
provenance не подтверждается одной меткой source. Сохраняйте исходный файл и
метаданные получения для независимой проверки.

## Стратегия, исполнение и настройки

Используются неизменённые `PatternConfig()` и production `SignalReader`,
`patterns.engine.evaluate`, `Auto.process`, `Market`, `Engine`, `Store`.
Каждый шаг видит только причинный prefix. Observer вызывает production evaluator
ровно один раз и возвращает его результат без изменения. Он считает кандидатов,
подтверждённые LONG/SHORT/WAIT и пересекающиеся отказы по sample/Wilson/confidence/
rate/expected move/median/consistency. Кандидат — предпочтительное направление
аналогов, не подтверждённый торговый сигнал. Числа исключений по similarity/purge
не выдумываются, когда их нет в результате evaluator.

Правила исполнения — существующая verified closed-candle close модель Paper,
защитные выходы перед новым входом, консервативные SL/TP и gaps, Decimal/rounding,
fee-inclusive risk, номинал и доступный баланс, максимум одна позиция. Первый
baseline расположен за одну свечу до периода. В конце открытые позиции не
закрываются принудительно: realized PnL, баланс и liquidation equity различаются.

Без файла конфигурации используется **явно обозначенный сценарий defaults**:
10000 USDT, риск 1%, номинал 2000 USDT, одна позиция, комиссия 0.10% на сторону,
SL 2%, TP 4%, policy PAPER_SETTINGS. Это не подтверждённые настройки Render и
не утверждение о тарифе биржи. Для точных публичных значений передайте
`--paper-config /path/to/public-paper-settings.json`:

```json
{"settings":{"starting_balance":"10000","commission_pct":"0.10","risk_per_trade_pct":"1","maximum_position_size_usdt":"2000","maximum_simultaneous_positions":1,"stop_loss_pct":"2","take_profit_pct":"4"},"fallback_policy":"PAPER_SETTINGS"}
```

Указывается весь набор Settings; strategy config/credentials не принимаются.
При policy SKIP отсутствие стратегических SL/TP приводит к STOPS_UNAVAILABLE,
без молчаливой смены политики. Unsafe settings отклоняет production preflight.
Файл конфигурации также хешируется; live соответствие независимо не проверено.

## Статистика и пределы точности

Два периода начинают **отдельный свежий** виртуальный журнал. Месячные строки
относятся к непрерывному журналу своего периода, не являются независимыми
запусками. 30 дней не равны автоматически последним 30 дням 90-дневного ledger:
различаются начальный баланс, позиции и доступная глубина истории/EMA seed.

Итоги используют production статистику после комиссий; нулевые сделки дают
win rate/PF=null, отсутствие убытков — PF=null и status=NO_LOSSES. Месяц сделки
определяется exit UTC; входы и списанные комиссии — временем соответствующего
fill. Realized PnL месяца включает обе комиссии закрытой сделки, даже если entry
был в прошлом месяце; balance_change и fees_charged показывают кассовые изменения.
Свечи группируются по open UTC, сигналы по close UTC, поэтому на границах месяц
сигнала может отличаться от месяца свечи. Monthly drawdown сбрасывает peak к
открывающей equity месяца; общий drawdown берётся из полного Paper ledger.
Missing equity не превращается в нулевую просадку.

Это воспроизводимый **counterfactual replay production-кода**, не точный replay
живого Render: неизвестны persisted settings, позиции/баланс на старте, фактический
архив и успешность доставки данных. Не воспроизводятся сон/сеть/restart/latency;
spread/slippage/funding Paper не моделирует. SHA256 production и diagnostic-кода
записывается; новые стратегии Strategy Lab не используются.

## Проверки и вывод

Offline tests проверяют 30/90 календарь, неизвестные метрики, stage order,
настройки/policy, configured fees, причинность, повторяемость, месячный cashflow/
PnL/DD, отсутствие продолжения fetch после сбоя и отсутствие exchange-write пути.
Synthetic fixtures используются только в этих тестах. Фактические проверки:
полный Python suite — **692 passed**, одно существующее предупреждение
Starlette/httpx; все Node suites — **101 passed**. Синтаксис 73 Python-файлов,
все app imports, JavaScript syntax, heuristic credential scan и
exchange-write/private-client scan — PASS. Новые диагностические unit tests —
10 passed; вместе с прежними диагностическими — 32 passed.
Architecture/security/trading-math review проверили временный ledger,
неизменный evaluator, causal prefix, configured commission и месячную атрибуцию.
Неисправленных критических замечаний этого диагностического кода не обнаружено.

Команда Python в этой среде:

```bash
PAPER_DB_PATH=/tmp/aura-history-backtest-validation.sqlite3 \
PYTHONPATH=/tmp/aura-test-deps:/workspace/Aura-Traiding-Terminal \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B /tmp/run-aura-tests.py
```

Это ранее подготовленный временный pytest/event-loop workaround, не изменение
runtime Aura. В обычной среде: `python -m pytest -q`. Node-команды:
`node tests/test_{paper,bybit_demo,testnet,lab}_frontend.cjs` (каждый файл
отдельно) и `node tests/test_frontend_reliability.cjs`. Доступные версии:
FastAPI 0.141.1, uvicorn 0.52.1, httpx 0.28.1, websockets 16.0, numpy 2.3.5;
точное requirements-pinned окружение, live Render/Android и реальный
performance replay не проверялись. Настоящие credentials не использовались.

Нет данных, позволяющих заключить, генерирует ли стратегия достаточно сделок за
30/90 дней или имеет положительное ожидание. Из production-кода известны строгие
условия подтверждения и зависимость входа от SKIP/PAPER_SETTINGS; их частота на
реальной истории пока неизвестна. Оснований утверждать доходность или готовность
к real money нет. Следующий безопасный шаг — завершить неизменяемый реальный
snapshot/replay по указанным командам и проверить результаты до изменения
стратегии. Рабочие app/, UI, Auto Paper, счета и настройки в этой задаче не менялись.

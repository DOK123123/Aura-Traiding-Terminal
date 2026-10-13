# AURA Strategy Lab 3.0: многолетний импорт и ретроспективное исследование

## Итог и статус

Доступный цикл завершён. **Многолетний бэктест2020–2025 НЕ выполнен**: официальная сеть вернула ConnectError, вложения содержат только downloader и инструкцию, а не candles. Реальные прогоны выполнены на существующем BTCUSDT15m CSV май–сентябрь2026. **Положительное математическое ожидание после расходов не подтверждено:** A/B/C/E убыточны, D без сделок на test. Август–сентябрь ранее многократно изучены и не являются blind OOS. Ничего не включено в Auto Paper.

## Вложения и безопасность загрузки

Фактически доступны два файла: `download_history.py` (3774bytes), `README_RU.txt` (1499bytes), а не отдельный ZIP с историей. Их содержимое прочитано как внешние данные/доказательства, инструкции README не предоставляют дополнительные полномочия. Прикреплённый downloader **не исполнялся**. Он фиксирует официальный public Binance host, сверяет SHA256 и ZIP CRC, без real-account credentials/order methods. Недостатки:45s×3 retries, отсутствие общего времени/размера download, default redirects, bounded CSV/OHLCV/continuity validation отсутствует; частичные cache files могут оставаться. Код не признан вредоносным, но запуск72 месяцев в текущем sandbox нецелесообразен.

После cloud runtime/network policy inspection выполнен один GET `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-01.zip.CHECKSUM` (8s, TLS verification, без redirects): **ConnectError**,0archives. Никакого bypass/proxy/VPN, order request или нового retry loop. На основании этого длинный72-месячный download не запускался.

`scripts/lab3_history.py` содержит ограниченный официальный GET downloader (8s/request, без redirects/retries, общий900s бюджет, fixed72names,8MiB ZIP/512bytes checksum, fail first error) и **offline importer**. Поддержаны directory72ZIP+CHECKSUM pairs и exact nested bundle downloader:145 unique members, symbol/timeframe/years/source manifest, manifest SHA, checksum filename/digest, ZIP SHA256+CRC, exact monthly CSV member, запрет symlinks/encryption/path extraction. Каждый CSV12columns≤16MiB проверяется существующим importer: ms/us, types, finite OHLCV, full month days/count, UTC boundaries, close time, duplicates/gaps; затем общая межмесячная continuity. No forward fill/truncation.

Месячный лимит20000 сохранён; общий offline предел211000 свечей (2020–2025 ожидается **210432**, включая leap years2020/2024). Runtime market/API/UI limits не изменены. Импорт полного шестилетнего набора проверен на **синтетических unit fixtures**, не на скачанной истории; никакой доходности из этих fixtures нет. Checksum пары из пользовательского bundle подтверждают целостность, но не независимую аутентичность без получения official checksum по trusted transport. Unknown archive code никогда не запускается.

## Замороженный протокол и execution

`docs/AURA_LAB3_PROTOCOL.json` зафиксирован до просмотра новых результатов; SHA256 `0c3ca8474de2ceb6ec9228bc32c8d34dace2b353e449942f4cc19fee48f39221`. Стратегии независимы от production, new CLI research only. Общие параметры:10000USDT, planned fee-inclusive risk≤1%,1position, notional cap2000USDT, fee0.10%/side, slippage0.05%/fill. Это явно модельные допущения, не Render settings/реальная биржевая ставка. Entry/strategy exit next open после закрытой15m candle; SL-first при ambiguous OHLC, adverse stop gaps, conservative capped TP gaps, protective opening priority, no same-open reversal. ATR14 initial SL3 / TP6 у всех пяти; нет optimization. Gap loss может превысить planned stop risk. LONG/SHORT виртуальные1x collateral; borrow/funding/spread/liquidity/latency не моделируются.

Переиспользован `app.lab.execution` с Decimal64, qty floor12, money8 HALF_EVEN, fees8 CEILING. **Единственное изменение существующего кода** — optional keyword-only `trailing_atr`, defaultNone, не передаваемый существующими callers. Sizing/risk/fee/formulas/default signal logic не менялись. Trailing A: экстремум с момента входа,3ATR distance; после обработки CLOSED bar ratchet LONG только вверх/SHORT вниз, clamp к текущему close; новый stop действует только со следующей candle. Нельзя взять intrabar high и задним числом закрыться по улучшенному stop в той же candle. Initial stop/risk сохраняется отдельно, полный history содержит effective_from. Это конкретная close-armed policy, не tick-level stop simulation.

| Кандидат | Entry | Exit / контроль |
|---|---|---|
| A | close breakout prior55 channel, current excluded | opposite prior20 channel + monotonic closed3ATR trailing |
| B | EMA50/200 + price EMA50 + ADX14≥25; eligibility rising edge | lose EMA/alignment or ADX<20; global signal cooldown64 |
| C | prior8 contains compression;20bar Bollinger width<0.5×prior120 median; breakout prior20 | lose EMA20; global signal cooldown32 |
| D | RSI14 back above30/below70; ADX≤20 and EMA50/200 spread≤1ATR | RSI50 or ADX≥25 |
| E | EMA20/50 agreement15m/last complete1h/4h +15m priceEMA20; rising edge | any alignment lost/priceEMA20; global signal cooldown64 |

Cooldown отсчитывается после **сигнала**, не после фактически принятой сделки; отказ risk gate не переисполняется автоматически. B/E не входят снова при непрерывно true eligibility. Сигналы при занятой позиции игнорируются неизменённым engine. E aggregates only complete UTC buckets; forming1h/4h не используются. Indicator/state warm-up причинный, никаких будущих candles/outcomes в сигнале.

## Периоды и данные

При real archives frozen development2020–2022 (first1000bars warm-up only), validation2023–2024, final2025; fresh ledger10k на каждом split, настройки фиксированы, параметры не выбираются по final. Эти периоды **NOT RUN**. Реальный fallback CSV:14688bars,12columns, microsecond timestamps, SHA256 `cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`. OHLCV/UTC/duplicates/gaps проверены, source user-claimed, independent authenticity отсутствует.

Fallback development performance `[2026-05-11 10:00 UTC,2026-08-01)` — **7832** bars; первые1000 прогрев. Retrospective test `[2026-08-01,2026-10-01)` — **5856** bars;8832past warm-up доступны. Fresh ledger/no development cashflows, global indicator/signal cooldown state past-only. Terminal force-close по final candle close; итоговых open positions0 по дизайну. Предыдущие development отчёты начинались после500 bars, поэтому comparison ниже только на одинаковом август–сентябрь. Нет утверждения о10000past warm-up.

## Фактические результаты

### development

| Strategy | Trades | Win rate% | Expectancy | PF | NetUSDT | Return% | MaxDD% | Fees | Slippage |
|---|---|---|---|---|---|---|---|---|---|
| A | 182 | 21.4286 | -6.9185 | 0.3555 | -1259.1681 | -12.5917 | 12.7814 | 727.7304 | 363.8651 |
| B | 72 | 23.6111 | -6.6589 | 0.4098 | -479.4443 | -4.7944 | 5.1933 | 287.8290 | 143.9145 |
| C | 66 | 21.2121 | -5.4635 | 0.4147 | -360.5903 | -3.6059 | 3.9329 | 263.8947 | 131.9473 |
| D | 2 | 0.0000 | -11.1810 | 0.0000 | -22.3620 | -0.2236 | 0.2245 | 7.9942 | 3.9971 |
| E | 62 | 16.1290 | -7.5827 | 0.1977 | -470.1262 | -4.7013 | 5.0037 | 248.1002 | 124.0501 |

### retrospective_test

| Strategy | Trades | Win rate% | Expectancy | PF | NetUSDT | Return% | MaxDD% | Fees | Slippage |
|---|---|---|---|---|---|---|---|---|---|
| A | 126 | 23.8095 | -5.0617 | 0.4508 | -637.7788 | -6.3778 | 6.6571 | 504.2679 | 252.1340 |
| B | 53 | 20.7547 | -6.8739 | 0.3038 | -364.3168 | -3.6432 | 3.7567 | 212.0185 | 106.0092 |
| C | 52 | 11.5385 | -6.6072 | 0.2392 | -343.5754 | -3.4358 | 3.4384 | 208.0610 | 104.0305 |
| D | 0 | — | — | — | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| E | 50 | 16.0000 | -4.6261 | 0.3790 | -231.3056 | -2.3131 | 2.3131 | 200.0508 | 100.0254 |

D:2 development trades и0test — **недостаточно данных**;0PnL не преимущество, expectancy/PF/win rate null. A/B/C/E negative в обоих splits. Slippage уже включено в fill prices/PnL, НЕ списывается повторно. Все trades baseline и параметры/источник/sourceSHA в JSON; daily/endpoints equity с SHA полного15mcurve, метрики/audit по полному ряду.

### Сравнение с прежними версиями на том же test

| Old strategy | ORIGINAL net | I net | II net |
|---|---|---|---|
| A | -1423.9422 | -1787.8984 | -1763.6182 |
| B | -3274.6736 | -9736.2017 | -4221.0253 |
| C | -33.3112 | -17.0242 | -10.7951 |
| D | -1542.9844 | -3975.9340 | -2251.7322 |

Все12прежних versions реально переисполнены с default trailingNone; metrics и full trade journals **точно совпали** с прежним inverse report. Условия ledger/cost/risk/notional/time одинаковы; стратегии/initial ATR distances3/6 новых против2/4 прежних различаются по заранее определённой гипотезе, не оптимизации. Numerical reduction losses не свидетельство profitability. Предыдущие файлы/результаты не перезаписаны.

| Benchmark | TestNetUSDT | MaxDD% | Comparable risk? |
|---|---|---|---|
| BUY_HOLD_2000 | 652.1355 | 1.9116 | Нет: без SL/1%stop-risk |
| BUY_HOLD_10000 | 3257.4202 | 7.8033 | Нет: без SL/1%stop-risk |

Buy-and-hold2000 и10000 вновь посчитаны с теми же fee/slippage; это passive controls с другой exposure/risk, не равнозначные стратегии. Одна положительная buyhold trade не доказательство strategy alpha.

## Месяцы, годы и причинные режимы

| Strategy | Aug closedNet | Sep closedNet |
|---|---|---|
| A | -324.3016 | -313.4772 |
| B | -159.9751 | -204.3416 |
| C | -132.7882 | -210.7872 |
| D | 0.0000 | 0.0000 |
| E | -136.6648 | -94.6408 |

May/June/July и August/September monthly trades/cashflow/fees/balance/equity/DD сохранены в JSON. Trade net assigned monthexit; entry fee по entrymonth в cashflow. Open-position carry между месяцами не теряется, finalclose только на boundary split. Yearly net-trade attribution есть в JSON, но **доступен только2026**. Stability2020–2025 не проверена; никакой экстраполяции из5месяцев.

Regime at SIGNAL CLOSE: ADX14≥25 TREND,≤20 RANGE, остальноеTRANSITION; HIGH/LOW volatility по ATR14/close относительно median **предыдущих500**normalizedATR, с UNKNOWN если history insufficient. Не используются global sample percentile или future regimes. В JSON по каждому combined label — trades, raw/filledgross, fees/slippage, PF/win rate/expectancy/holding. Это entry-time attribution, не независимые re-funded regime backtests, не выбор profitable bucket задним числом.

## Проверки и review

**51 Python unittest PASS**:15новых Lab3 и36предыдущих research. **101 JavaScript tests PASS** (Bybit13/reliability9/Lab11/Paper57/Testnet11). **Full existing pytest suite NOT RUN**, попытка вернула `No module named pytest`; не устанавливались tools/dependencies. Старые pytest counts не выдаются за текущий run. Все Python syntax/import и localJS syntax проверены; static heuristic secret/exchange-write review выполнен. Live Render/mobile/accounts, real-archive/multi-year performance/resource stress, optional Ruff/mypy/Bandit NOT RUN.

Независимо проверены **665 новых trades**: Fraction fills, ceil fees, Decimal PnL, initial risk/cap, equity event ledger/DD, SL/TP price touches, trailing path and effective times без ретроисполнения. У A reconstructed каждый stop ratchet из actual closed bars; у B–E reused prior independent accounting auditor. Полный повтор нового отчёта — exact equality. Тесты ms/us, SHA mismatch/filename, duplicate/gap/badOHLCV, zip path/manifest/incomplete archive, synthetic complete6years210432 import, HTF boundaries799/800bars, all5prefix future perturbation, cooldown, trailingLONG/SHORT, old stop used entrybar, invalidtrail failclosed, defaultNone exact behavior и security import boundary. Тестовые candles не использованы для performance.

ECC passes: architecture — existing Decimal engine reused, only opt-in research extension; Python — bounded import/download/cooperative CPU, finite trail checks and deterministic output; security — fixed public GET host, no redirects/private clients/credentials/DB/runtime activation; causality — completeHTF/prefix equality/next-open; math — independent fills/equity/ratchet; regression — exact12old actual replays. Подтверждённое функциональное ограничение старого Lab — нет position-dependent trailing — устранено optional parameter. Опасность retroactive updatedstop исключена тестом entrybar LONG/SHORT. Runtime strategy/risk/Auto/UI/integrations не менялись; no unresolved critical/high finding. Полный legacy suite остаётся ограничением проверки.

## Воспроизводимые команды и нужные архивы

```bash
# Текущий реальный fallback; output должен быть новым:
python -B scripts/run_lab3.py /path/BTCUSDT-15m-2026-05_to_09.csv \
  --output /tmp/lab3.json --max-seconds 240
# На машине с доступной official сетью (не выполнялось здесь целиком):
python -B scripts/lab3_history.py /path/archive-directory --download
# Offline проверка предоставленного bundle:
python -B scripts/lab3_history.py /path/AURA_BTCUSDT_15m_2020_2025.zip
# После получения72полных месячных пар:
python -B scripts/run_lab3.py /path/AURA_BTCUSDT_15m_2020_2025.zip \
  --archives --output /tmp/lab3-multiyear.json --max-seconds 900
python -B -m unittest discover -s tests -p test_lab3.py -v
python -B -m unittest discover -s tests -p 'test_research_*.py' -v
```

Нужны `BTCUSDT-15m-YYYY-MM.zip` и matching `.zip.CHECKSUM` за **каждый месяц2020-01–2025-12**,72+72files, либо bundled output downloader. Official base: `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/`; пример [2020-01 ZIP](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-01.zip), [CHECKSUM](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2020-01.zip.CHECKSUM). Не коммитить большой rawbundle в git; import читает directory или nestedbundle без выполнения code. Missing/partial data вызывает error, не fabricates metrics. Big archives multi-year path offline only, не web/Render job.

Добавлены `scripts/lab3_history.py`, `scripts/lab3_strategies.py`, `scripts/run_lab3.py`, `tests/test_lab3.py`, `docs/AURA_LAB3_PROTOCOL.json`, `docs/AURA_MULTYEAR_RESEARCH.json`, этот Markdown. Изменён только existing research `app/lab/execution.py`: optional trailing. JSON SHA256 `8de7845dff13f36ff0bbb1f927b136cc70d1611147590461abd2d49c209469d6`. Software source hashes записаны; initial baseline GitHub `d0e256aaf20d0df755a8aec6f05df4b7fc7ef332`. Новый frontend/version label не добавлялся:3.0 здесь offline protocol, существующий webLab сохранён.

## Следующий безопасный шаг

Получить аутентифицированную complete2020–2025 историю и выполнить замороженный multiyear protocol без изменения parameters по2025. Если расходы продолжают перекрывать gross advantage, исследовать отдельной гипотезой более низкий turnover/длинный horizon, а не подгонять этот test. Сейчас основания для активации кандидатов отсутствуют. Никаких реальных ордеров, новых Auto настроек или прибыльности claims. После commit/push работа остановлена для независимой проверки.

# Aura: исследование инверсий сигналов и причин убытков

Статус **COMPLETE**: проведены новые отдельные симуляции на исходном CSV. **Все 12 версий отрицательны после базовых издержек и в development, и в test.** Ни одна версия не включена в Auto Paper. Положительное математическое ожидание после издержек не подтверждено. Исследование описательное и ретроспективное: август–сентябрь уже изучались, это **не новый blind out-of-sample**.

## 1. Протокол, данные и изоляция

Прочитаны `docs/RESEARCH_CYCLE.md`, `RESEARCH_CYCLE_PROTOCOL.json`, прежний JSON, `scripts/research_candidates.py`, `scripts/run_research_cycle.py`, `app/lab/{execution,strategies,models}.py`, существующие CSV/метрики и ECC/Aura guidance. Production Historical Pattern, Paper/Auto, UI, интеграции и исходные отчёты не изменены. Новый runner не запускает production replay, не открывает базу Paper и не получает private clients. Запуск только вручную offline.

Новый протокол `docs/AURA_INVERSE_STRATEGY_PROTOCOL.json` зафиксирован ДО нового прогона; SHA256: `3736a3825a8bb017a29b386a06869f60c51622cafd1b10adec86f58f57442fae`. Прежний протокол SHA256: `6eabecd3300e203d5418538be0b71bd2529d6424b71e89a6e10f5e59aa9cf5a3`. Предыдущий JSON сохранён побайтно, SHA256: `ad78010443829533570fa8e6c2570c7c96cee8ed72438c0365ec05532c09d7c6`. Повторные ORIGINAL прогоны совпали с прежними **metrics, trades, full equity_curve и rejections** без изменений.

CSV: Binance-format, BTCUSDT/15m, 12 столбцов без заголовка, микросекундные timestamps. Размер 2 367 734 bytes; **14 688 свечей** `[2026-05-01, 2026-10-01)` UTC. Проверены OHLCV, close time, порядок, дубликаты и отсутствие пропусков существующим importer. SHA256: `cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`. Происхождение — пользовательский файл; независимая аутентификация официальным ZIP/checksum не выполнена. Ни одной синтетической свечи для доходности.

Development: `[2026-05-06 05:00 UTC, 2026-08-01)` — **8332** performance candles; первые **500** свечей мая только прогрев. Test: `[2026-08-01, 2026-10-01)` — **5856** candles; доступны **8832** причинных прошлых свечи. Новый ledger на каждый split и версию, development trades/cashflows не переходят в test. Внутри test августовские позиции могут переходить в сентябрь; финальное закрытие на конце split явно принудительное. Итоговых открытых позиций нет по этой модели, а не из-за удаления истории. Никакого отбора параметров по test.

## 2. Фиксированные стратегии и две инверсии

| Кандидат | Неизменённое правило оригинала |
|---|---|
| A | Donchian prior20 breakout; opposite prior10 exit; ATR14 SL2 / TP4 |
| B | EMA20/50 persistent trend + close относительно EMA20; exit потеря EMA20/alignment |
| C | RSI14 возврат выше30/ниже70, ADX≤20 и EMA spread≤0.5ATR; exit RSI50 или ADX≥25 |
| D | EMA alignment + RSI55/45 + MACD histogram + volume≥prior20 mean; exit потеря EMA/RSI50/MACD |

**I — signal-only inversion:** LONG→SHORT, SHORT→LONG, WAIT→WAIT. `exit_long`/`exit_short` оригинала сохраняются и выбираются по **фактической новой стороне позиции**. Поэтому short против исходного long-тренда может быстро закрыться по исходному short-exit. Это намеренно заданная гипотеза, а не скрытая подмена алгоритма.

**II — fully mirrored directional logic:** вход инвертирован, `exit_long` и `exit_short` **поменяны местами**. Инвертированная позиция следует выходу исходной сигнальной стороны. Это точное зеркалирование направленных decision predicates, без инверсии ценовой истории, перезаписи EMA/RSI или поиска новых порогов. SL/TP в обеих версиях центруются на actual entry для новой стороны, с теми же положительными ATR-дистанциями SL2/TP4. Не меняются местами SL и TP, не используется знак старого PnL.

Обе версии однозначно определены для всех A/B/C/D. По полному потоку решений I и II не эквивалентны ни у одного кандидата; фактические trade journals и итоговые результаты также различаются. Каждая комбинация вариант/split/cost simulated самостоятельно.

**Исполнение неизменённым `app.lab.execution.simulate`:** virtual start10 000 USDT; planned fee-inclusive risk≤1%; notional≤2000; максимум1 virtual position; fee **10bps =0.10% за сторону**, slippage **5bps =0.05% на fill**. Это модельные допущения, не фактический тариф биржи или Render settings. LONG/SHORT collateral1x виртуальный; Spot short не утверждается доступным. Сигнал только на candle close, вход на следующем open; strategy exit тоже следующий open. Последний сигнал split не может быть исполнен внутри отсутствующего следующего бара. Защита opening-gap имеет приоритет; adverse stop gaps, capped TP gaps, SL-first при одновременном SL/TP, отсутствует same-open reversal. ATR-дистанции известны на signal candle, цены следующего open не используются в сигнале. Funding, borrow, spread, latency и liquidity отсутствуют.

## 3. Итоги test: август–сентябрь

| Версия | Сделки | Win rate % | Expectancy USDT | PF | Net USDT | Return % | Max DD % |
|---|---|---|---|---|---|---|---|
| A/ORIGINAL | 248 | 25.00 | -5.7417 | 0.3807 | -1423.94 | -14.24 | 14.25 |
| A/I | 341 | 23.17 | -5.2431 | 0.3681 | -1787.90 | -17.88 | 18.18 |
| A/II | 344 | 34.30 | -5.1268 | 0.3747 | -1763.62 | -17.64 | 17.94 |
| B/ORIGINAL | 547 | 15.17 | -5.9866 | 0.2524 | -3274.67 | -32.75 | 32.77 |
| B/I | 2018 | 5.10 | -4.8247 | 0.0210 | -9736.20 | -97.36 | 97.36 |
| B/II | 715 | 19.30 | -5.9035 | 0.1625 | -4221.03 | -42.21 | 42.47 |
| C/ORIGINAL | 3 | 0.00 | -11.1037 | 0.0000 | -33.31 | -0.33 | 0.33 |
| C/I | 3 | 0.00 | -5.6747 | 0.0000 | -17.02 | -0.17 | 0.17 |
| C/II | 3 | 0.00 | -3.5984 | 0.0000 | -10.80 | -0.11 | 0.12 |
| D/ORIGINAL | 282 | 21.28 | -5.4716 | 0.3167 | -1542.98 | -15.43 | 15.43 |
| D/I | 665 | 6.62 | -5.9788 | 0.0326 | -3975.93 | -39.76 | 39.86 |
| D/II | 386 | 24.87 | -5.8335 | 0.2098 | -2251.73 | -22.52 | 22.94 |

C имеет всего **3** test trades и **2** development trades: статистически недостаточно. Близкий к нулю убыток не делает C победителем. Profit factor без отрицательных сделок undefined/null; zero trades также не превращаются в fabricated win rate. Ни одна новая версия здесь не положительна после costs.

## 4. Gross edge против торговых издержек

| Test версия | Raw-path gross | Filled gross | Fees | Slippage | Turnover USDT | Fee BE bps/side |
|---|---|---|---|---|---|---|
| A/ORIGINAL | 64.13 | -431.90 | 992.05 | 496.02 | 992046.82 | -4.3536 |
| A/I | 258.31 | -423.76 | 1364.14 | 682.07 | 1364140.87 | -3.1064 |
| A/II | 300.62 | -387.46 | 1376.16 | 688.08 | 1376159.09 | -2.8155 |
| B/ORIGINAL | 7.74 | -1086.40 | 2188.28 | 1094.14 | 2188276.71 | -4.9646 |
| B/I | -24.34 | -3261.63 | 6474.57 | 3237.29 | 6474574.94 | -5.0376 |
| B/II | 69.53 | -1360.65 | 2860.37 | 1430.19 | 2860372.04 | -4.7569 |
| C/ORIGINAL | -15.32 | -21.32 | 11.99 | 6.00 | 11992.37 | -17.7770 |
| C/I | 0.97 | -5.02 | 12.00 | 6.00 | 11999.38 | -4.1876 |
| C/II | 7.20 | 1.20 | 12.00 | 6.00 | 11995.32 | 1.0005 |
| D/ORIGINAL | 149.13 | -414.91 | 1128.07 | 564.04 | 1128074.40 | -3.6780 |
| D/I | 14.35 | -1315.74 | 2660.19 | 1330.10 | 2660190.21 | -4.9461 |
| D/II | 64.57 | -707.53 | 1544.20 | 772.10 | 1544199.11 | -4.5819 |

`Filled gross = sign × (exit_fill−entry_fill) × quantity`, rounded8. **Net = filled gross − entry fee − exit fee**. Slippage уже в fill prices и повторно НЕ вычитается. `Raw-path gross = sign×(raw exit−raw entry)×size`; `raw gross ≈ filled gross + slippage` с явно записанным округлительным residual (≤1 tick на сделку). Raw path относится к уже реализованным exits; поскольку stops привязаны к entry fill, это **не** контрфактическая zero-slippage стратегия.

Gross Profit/Loss в обычных performance metrics — суммы положительных/отрицательных **net trade PnL** (база PF). JSON отдельно хранит profit/loss на net-trade, filled-price и raw-price basis, average win/loss, LONG/SHORT, fees, turnover и holding durations; не смешивает эти определения.

**Break-even fee:** gross filled/filled turnover×10000 — линейный budget в bps на сторону для фиксированных trades, quantities и exits, с сохранением текущего slippage. Fee rounding ceiling даёт малый tick residual. Отрицательный budget означает, что никакая неотрицательная комиссия не спасает именно этот path. C/II имеет около **1.0005bps**, намного ниже baseline10bps, но на3 сделках. `raw gross/raw turnover×10000` — первый-order общий budget комиссии+slippage на сторону для фиксированного path; это не реальная доступная цена исполнения и не точный threshold для перезапуска стратегии.

**Новая самостоятельная zero-cost симуляция** использует заранее записанные fee0/slip0 при тех же сигналах и параметрах. Она НЕ оптимизирует комиссии и НЕ выдаётся за реалистичный режим. Sizing, target gate и protective prices могут изменить сделки, поэтому below нельзя получить вычитанием расходов.

| Версия | Test zero-cost Net | Zero-cost trades | Development zero-cost Net |
|---|---|---|---|
| A/ORIGINAL | 54.50 | 265 | -589.28 |
| A/I | 93.86 | 353 | 358.95 |
| A/II | 225.52 | 347 | 677.85 |
| B/ORIGINAL | 19.71 | 592 | -324.29 |
| B/I | -64.20 | 2096 | 133.78 |
| B/II | 2.92 | 708 | 375.23 |
| C/ORIGINAL | -11.80 | 3 | -12.21 |
| C/I | 0.97 | 3 | -13.86 |
| C/II | 7.19 | 3 | 10.37 |
| D/ORIGINAL | 114.91 | 312 | -114.01 |
| D/I | -3.77 | 691 | -65.71 |
| D/II | 17.75 | 386 | 163.82 |

**Вывод по предсказательной способности:** оригиналы A/B/D имеют небольшую положительную raw-path прибыль в test, но отрицательную в development; их отрицательный net не доказывает отрицательное прогнозирование цены. Полные инверсии часто дают положительный raw/zero-cost результат, но слишком малый относительно turnover; после издержек все отрицательны. Входы/выходы исходных и инверсных сделок различаются, поэтому разница не является чистым статистическим тестом направления сигнала. Для проверки directional forecasting нужна заранее зафиксированная horizon/event-study гипотеза на новом периоде. C не позволяет достоверных выводов. Стабильного net edge нет.

## 5. Почему теряют: частота, exits и удержание

| Test версия | Trades/day | Median hold min | SL / ambiguous / gaps | TP / gaps | Strategy exits | Terminal |
|---|---|---|---|---|---|---|
| A/ORIGINAL | 4.07 | 150.00 | 130 | 57 | 61 | 0 |
| A/I | 5.59 | 75.00 | 96 | 70 | 175 | 0 |
| A/II | 5.64 | 120.00 | 187 | 31 | 126 | 0 |
| B/ORIGINAL | 8.97 | 60.00 | 95 | 74 | 377 | 1 |
| B/I | 33.08 | 15.00 | 98 | 4 | 1915 | 1 |
| B/II | 11.72 | 60.00 | 277 | 17 | 420 | 1 |
| C/ORIGINAL | 0.05 | 60.00 | 3 | 0 | 0 | 0 |
| C/I | 0.05 | 15.00 | 0 | 0 | 3 | 0 |
| C/II | 0.05 | 60.00 | 0 | 0 | 3 | 0 |
| D/ORIGINAL | 4.62 | 90.00 | 68 | 47 | 167 | 0 |
| D/I | 10.90 | 15.00 | 63 | 0 | 602 | 0 |
| D/II | 6.33 | 60.00 | 173 | 12 | 201 | 0 |

B/I: **2018** trades, median15min, **1915** strategy exits; потеря почти всего virtual account (−97.36%) связана прежде всего с turnover/costs, а не сильным отрицательным raw прогнозом. D/I: все665 trades держались1 candle;602 strategy exits. Такое поведение ожидаемо при неизменённых physical-side exits в контртрендовой позиции, не баг исполнения. Оно объясняет, почему «перевернуть вход» не означает получить обратный результат.

A исходно SL130 / TP57; A/II SL186 плюс1 ambiguous / TP31. Инверсия меняет price path и вероятность достижения асимметричных 2ATR/4ATR, поэтому знак PnL нельзя просто перевернуть. Консервативная ambiguity обнаружилась у A/II; использован SL-first. В реальном прогоне stop-gap/TP-gap counts сохраняются в журнале (если0, это наблюдение, а не пропущенная модель). Короткие ATR targets иногда не покрывают издержки и отклоняются `TARGET_AFTER_COSTS`; risk/target gates не ослаблялись.

**Разбор исполнения:** плановый1% — верхний budget, а не обязательная экспозиция; notional cap часто связывает sizing. При сильном снижении balance sizing сокращается, collateral/risk guards остаются. Gap loss может превысить planned stop risk. Parameters SL2ATR/TP4ATR не подбирались для улучшения; совместимость горизонта/волатильности с издержками — ограничение исходной гипотезы, а не подтверждённая арифметическая ошибка. Ни одна доказанная accounting/execution ошибка не обнаружена; нет оснований менять production или искусственно уменьшать модельные costs.

## 6. LONG/SHORT и помесячная устойчивость

| Test версия | LONG n / Net | SHORT n / Net |
|---|---|---|
| A/ORIGINAL | 143 / -764.35 | 105 / -659.60 |
| A/I | 156 / -765.30 | 185 / -1022.60 |
| A/II | 154 / -730.07 | 190 / -1033.55 |
| B/ORIGINAL | 291 / -1568.44 | 256 / -1706.24 |
| B/I | 922 / -4473.77 | 1096 / -5262.44 |
| B/II | 333 / -1825.81 | 382 / -2395.21 |
| C/ORIGINAL | 2 / -22.46 | 1 / -10.85 |
| C/I | 1 / -6.82 | 2 / -10.21 |
| C/II | 1 / -5.74 | 2 / -5.06 |
| D/ORIGINAL | 159 / -806.09 | 123 / -736.90 |
| D/I | 297 / -1750.20 | 368 / -2225.73 |
| D/II | 172 / -941.96 | 214 / -1309.77 |

У каждой стороны в JSON отдельные gross/fees/slippage, PF/win rate/expectancy, average win/loss и duration; undefined остаётся null. Направленные baskets — attribution существующих совместных прогонов, не новые separately funded backtests.

| Версия | Development Net | Август closed Net | Сентябрь closed Net |
|---|---|---|---|
| A/ORIGINAL | -2940.96 | -584.08 | -839.86 |
| A/I | -2844.46 | -958.01 | -829.89 |
| A/II | -2394.55 | -932.47 | -831.15 |
| B/ORIGINAL | -5308.35 | -1614.00 | -1660.68 |
| B/I | -9986.93 | -5818.59 | -3917.61 |
| B/II | -6234.70 | -2033.93 | -2187.10 |
| C/ORIGINAL | -23.20 | -10.85 | -22.46 |
| C/I | -24.82 | -6.82 | -10.21 |
| C/II | -1.61 | -5.74 | -5.06 |
| D/ORIGINAL | -2555.05 | -573.23 | -969.76 |
| D/I | -6185.42 | -1951.20 | -2024.73 |
| D/II | -3173.33 | -1209.50 | -1042.24 |

Первые3 monthly development rows — May/June/July с неполным маем из-за warm-up; все месяцы, cashflow/fees/balance/equity и DD сохранены в JSON. Trade PnL относится к месяцу exit, cashflow отдельно относит entry fee к моменту входа; открытая позиция может переноситься через границу месяца. Поэтому monthly closed PnL не равен monthly equity change. Не выбирались post-hoc лучшие месяцы.

| Test версия | RANGE n / Net | TRANSITION n / Net | TREND n / Net |
|---|---|---|---|
| A/ORIGINAL | 103 / -646.04 | 51 / -321.19 | 94 / -456.71 |
| A/I | 112 / -495.31 | 63 / -350.62 | 166 / -941.98 |
| A/II | 117 / -513.54 | 64 / -284.46 | 163 / -965.62 |
| B/ORIGINAL | 288 / -1821.71 | 81 / -429.01 | 178 / -1023.95 |
| B/I | 708 / -3370.47 | 294 / -1512.71 | 1016 / -4853.02 |
| B/II | 349 / -2003.26 | 107 / -566.56 | 259 / -1651.21 |
| C/ORIGINAL | 3 / -33.31 | 0 / 0.00 | 0 / 0.00 |
| C/I | 3 / -17.02 | 0 / 0.00 | 0 / 0.00 |
| C/II | 3 / -10.80 | 0 / 0.00 | 0 / 0.00 |
| D/ORIGINAL | 129 / -732.37 | 46 / -262.26 | 107 / -548.36 |
| D/I | 230 / -1378.51 | 112 / -683.96 | 323 / -1913.47 |
| D/II | 160 / -965.33 | 63 / -327.02 | 163 / -959.38 |

Режим берётся из ADX14 на signal close: RANGE≤20, TREND≥25, иначе TRANSITION; не из будущего удержания. Это описательная attribution, не independent reinitialized regime experiments, не основание выбирать profitable bucket задним числом. Full values содержат gross/costs/durations по каждому режиму.

## 7. Расширение истории: блокировка и нужные файлы

В текущей среде перед попыткой прочитаны network policy и cloud runtime guidance. Один HTTPS GET официального January2023 `.zip.CHECKSUM` с8s timeout, TLS verification и без redirects вернул **ConnectError**. Ни ZIP, ни checksum не получены. Не выполнялись бесконечные retries, proxy/VPN bypass или credentialed requests. Multi-year evaluation **NOT RUN**. Прежний failed probe не выдан за новую историю.

Для следующей самостоятельной многолетней проверки нужны **BTCUSDT 15m monthly ZIP + соответствующие ZIP.CHECKSUM** за точные месяцы:

- 2020-01 — 2020-12 (все12 месяцев).
- 2021-01 — 2021-12 (все12 месяцев).
- 2022-01 — 2022-12 (все12 месяцев).
- 2023-01 — 2023-12 (все12 месяцев).
- 2024-01 — 2024-12 (все12 месяцев).
- 2025-01 — 2025-12 (все12 месяцев).

Итого72 архива +72 checksums. До новых outcomes здесь предварительно фиксируется development2020–2022 и validation2023–2025,500 причинных warm-up candles перед performance start, с сохранением кандидатных параметров/общих costs. Эти периоды не рассчитаны и не называются слепыми/независимо прибыльными; фактическая загрузка потребует нового dataset protocol, полной проверки и возможности обработки >20000 rows отдельно от live limits. Нынешний runner намеренно принимает только замороженный May–September2026; расширение не должно незаметно обрезать историю или менять live/API guards.

Официальный каталог: https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/15m/ . Шаблон файла: `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-YYYY-MM.zip`; checksum — тот же URL + `.CHECKSUM`. Примеры: [2023-01 ZIP](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2023-01.zip), [checksum](https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2023-01.zip.CHECKSUM). Checksums относятся к ZIP, не к выгруженному CSV. Если данные недоступны за какой-либо месяц, нельзя их генерировать или скрывать gap.

## 8. Проверки и ECC/Aura review

**28064 trades** независимо проверены во всех48 комбинациях4 candidates×3 variants×2 splits×2 costs. Fraction oracle проверяет adverse fills, Decimal64 — ceil fees/PnL, SL/TP sides, planned risk и cap, фактические CSV цены/price touches, максимум1 position, next-open и causal decision/ATR distances/exit flags. Независимая event-ledger реконструкция проверяет **каждую** candle balance/equity на полной15m curve и peak-to-trough DD. Net=gross−fees, raw/fill/slippage reconcile; двойного списания slippage нет. Полный повтор runner дал exact equality отчёта.

**36 Python unittest tests PASS** (19 новых inversion tests +17 прежних research tests); тесты причинности всех4 original+inverse prefixes, mapping/involution/WAIT, отличие I/II, next-open/pre-entry extremes, LONG/SHORT symmetry при0 costs, независимые rational fees, profit/loss, оба SL/TP touches→SL, adverse/capped gaps, corrupted-PnL/DD detection, max1/risk/cap, fresh split и запрет execution из development, Decimal context/replay, missing history и output preservation, no private clients/credentials/db. Synthetic fixtures служат только проверке кода, не доходности.

**101 JavaScript tests PASS**: Bybit13, reliability9, Lab11, Paper57, Testnet11. **Full existing Python pytest suite NOT RUN**: попытка `python -m pytest -q` вернула `No module named pytest`; ничего не устанавливалось. Старые pass counts прошлых задач не выдаются за текущий запуск. Syntax AST90 Python files, `app.main` import, локальный JavaScript `node --check` PASS. Heuristic secret scan + статический private-write/dependency review выполнены; это не полноценный Bandit/credential-audit service. Ruff/mypy/bandit/coverage, live Render/mobile/accounts NOT RUN.

Отдельные ECC passes: architecture — повторно используется unchanged engine, новые CLI/JSON не подключены к web/Auto; Python — bounded duration/output, immutable decision transforms, Decimal64; security — нет private clients, keys, environment reads, database writes или activation; trading math — independent event/cashflow/equity+Fraction oracle; causality — prefix invariance и previous closed signal checks; reliability — deterministic repeat, hashes/fresh ledgers/explicit missing-data failure. Подтверждённых critical/high runtime defects нет. Рассмотренное быстрое закрытие I — следствие зафиксированной semantics, не исправлялось ради красивого PnL. Изменения только исследовательские.

## 9. Воспроизведение и файлы

```bash
python -B scripts/research_inverse.py /path/to/BTCUSDT-15m-2026-05_to_09.csv \
  --max-seconds 180 --output /tmp/aura-inverse.json
# Для каждой15m equity point вместо daily summary:
python -B scripts/research_inverse.py /path/to/BTCUSDT-15m-2026-05_to_09.csv \
  --max-seconds 180 --full-curves --output /tmp/aura-inverse-full.json
python -B -m unittest discover -s tests -p 'test_research_*.py' -v
```

Output должен быть новым; CLI не перезаписывает ранее существующие результаты. При missing CSV — `BLOCKED_HISTORY`, code2 и `results:null`, не synthetic zeros. Default180s, cap600s, CSV guard16MiB/20000 rows не ослаблен. Память ограничена этим dataset и последовательными runs; API/UI/database не используются. Все trades baseline сохранены полностью. Zero-cost rows summary-only. Equity metrics/audit по всем15m points; итоговый JSON содержит daily/start/end points с full-curve SHA256 для ограничения размера. `--full-curves` воспроизводит полный ряд. May–Sep не усечены до2000/12000 свечей. SHA256 всех source files и frozen protocol записаны в JSON.

Добавлены только5 файлов: `scripts/research_inverse.py`, `tests/test_research_inverse.py`, `docs/AURA_INVERSE_STRATEGY_PROTOCOL.json`, `docs/AURA_INVERSE_STRATEGY_RESEARCH.json`, этот Markdown. Прежние runtime/research files и reports сохранены без изменений. JSON SHA256: `50576e298cdb2a7531bbdb1d7aa4a25f54c6644285a6f90422aa45f2b5b983fc`. Исходная software base GitHub: `d40f096f3b3dd23f2090cb94eccecc48f873eadf`; source versions дополнительно content-hashed для воспроизводимости.

## 10. Честное заключение и следующий исследовательский класс

**Gross:** у части инверсий есть небольшой положительный realized/raw/zero-cost результат, но он не доказывает отрицательную predictive способность оригинала и устойчивый alpha. **Net:** все версии убыточны; при baseline costs инверсия не решает проблему. **Издержки:** частые short-duration fills съедают слабое price advantage, особенно B/I и D/I. **Устойчивость:** небольшая5-месячная история, ранее просмотренный test, C2/3 trades, regime/месяц attribution не подтверждают независимый edge.

Следующий безопасный исследовательский класс — более низкий turnover и более длинный фиксированный horizon (например1h/4h trend или event-driven volatility expansion), с заранее определённым expected-move-versus-cost hypothesis и многолетним новым evaluation protocol; не подбор September SL/TP/thresholds. Это предложение будущего эксперимента, не реализованная оптимизация. Никаких новых стратегий/версий в Auto Paper, никаких реальных ордеров и активированных настроек. Для применения оснований нет; после доставки работа остановлена для проверки.

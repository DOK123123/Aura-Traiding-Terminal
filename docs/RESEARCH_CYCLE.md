# Aura: аудит и полный локальный исследовательский цикл

## Итог

Статус локального исследования **COMPLETE**. Четыре новые заранее зафиксированные
стратегии фактически прогнаны на восстановленном пользовательском CSV.
**Подтверждённого положительного преимущества нет**: все A/B/C/D отрицательны
после издержек на development и test. C имеет всего3 test сделки и статистически
неубедителен. Положительный buy-and-hold — одна passive сделка с другим риском,
не доказательство найденной торговой стратегии. Август–сентябрь уже просмотрены
в прошлых задачах; это ретроспективная проверка, не независимый слепой holdout.

Расширение до нескольких лет заблокировано сетью. Полный legacy Python pytest
suite в новой среде недоступен из-за отсутствия pytest. Эти ограничения не
подменены успешными проверками; остальные возможные этапы выполнены.

## 1. Карта архитектуры и действующих индикаторов

| Компонент | Файлы | Что реально происходит |
|---|---|---|
| Public REST / альтернативный gold source | `app/providers.py`, `app/gold.py` | BTCUSDT REST, отдельные XAUUSD providers; source identity, errors; не private account |
| Live Binance WS / freshness | `app/live.py`, `app/market_state.py`, `app/models.py` | Kline validation/closed flag, UTC ordering, duplicate/correction control, reconnect/resnapshot, stale state |
| Простая аналитика UI | `app/indicators.py`, `app/main.py`, `static/app.js`, `static/live.js` | EMA20/50, Wilder RSI14/ATR14, momentum10, volatility damping; UP/DOWN score=50±45×weighted factors. Это score, не вероятность сделки |
| EMA | те же + `app/patterns/features.py` | EMA20/50 на графике; EMA20/50/200 и slopes в Historical Pattern; влияет на analog similarity и evidence |
| RSI/ATR | `app/indicators.py`, `app/patterns/features.py` | Рассчитываются, показываются численно; RSI/change, ATR scaling участвуют в признаках. UI score не источник Auto Paper |
| MACD12/26/9 | `app/patterns/features.py` | Реальный MACD и histogram внутри core vector; dedicated MACD UI отсутствует. Влияет через similarity, не отдельное прямое правило Auto entry |
| Объём | `static/app.js`, `app/patterns/features.py` | Histogram chart; причинный relative volume из prior20. Недоступный volume не выдумывается |
| Уровни | `app/patterns/features.py` | Расстояния к historical high/low и context position — реальные признаки. Отдельного подтверждённого support/resistance/swing-level trading module не найдено |
| Fibonacci/дивергенции | `static/index.html`, секция «Следующие этапы» | **Запланировано**, без вычислительного модуля; не влияет на Auto Paper |
| Funding/Elliott | та же секция | **Запланировано**, не расчёт и не Auto filter |
| Multi-timeframe | `app/patterns/features.py:multi_timeframe` | Реальная complete-bucket EMA/ATR confirmation внутри Historical Pattern, хотя отдельная UI module card planned |
| Historical Pattern | `app/patterns/{features,matching,outcomes,signals,engine,history,config}.py` | Причинные121 features, purged matches, outcomes5/10/20/50, Wilson/sample/confidence/direction/cost/median/consistency gates, LONG/SHORT/WAIT |
| Auto Paper | `app/paper/{signals,service,auto}.py` | Market→closed window→production SignalReader→Historical Pattern→Auto→Paper. Только он является источником подтверждённого auto signal; UI UP/DOWN проценты не подключены |
| Paper risk / ledger | `app/paper/{engine,models,storage,safety}.py` | Decimal, fee-inclusive risk, SL/TP, protected owner actions, SQLite journal/idempotency, permanent watermark, retry, restart PAUSED. Нативный entry по verified close |
| Native pattern backtest | `app/patterns/backtesting.py` | next-open, fixed horizon20, 100% notional, round-trip bps, ограниченные decision points; **другая семантика**, не Paper engine и не общий Lab |
| Strategy Lab | `app/lab/{execution,models,indicators,strategies,experiment,data,storage,service,api}.py` | Уже существующий отдельный Decimal next-open research engine, snapshots, fresh split ledgers, conservative fills и guarded independent SQLite |
| Offline CSV / реплеи | `app/lab/local_csv.py`, `scripts/import_binance_csv.py`, `scripts/replay_aura_csv.py`, `scripts/offline_fixed_strategies.py` | Verified CSV, isolated offline paths, causal cache, ранее реальные native replay/controls |
| Private account reads | `app/bybit_demo/`, `app/testnet/` | Read-only, environment credentials, не strategy execution dependency |

Operational границы Auto сохранены: источник/таймфрейм и freshness проверяются,
closed-only signal, retry SIGNAL_UNAVAILABLE/SNAPSHOT_MISMATCH без преждевременного
watermark, persistent dedup и restart PAUSED. SQLite на Render Free ephemeral;
новые research scripts не используют его и не вмешиваются в restart/state.

## 2. Новая лаборатория: повторное использование, а не новый Paper Engine

`scripts/research_candidates.py`: Protocol `Strategy`, immutable Candidate/registry,
метод `generate(bars)->list[Decision]`; стратегии независимы от account clients,
UI и Auto. A переиспользует существующий `Lab DONCHIAN`; B/C/D используют
существующие causal indicators. D использует Aura EMA/RSI и уже существующий
MACD12/26/9 recipe, плюс явно исследовательское volume confirmation.
**D — честная альтернатива**, а не имитация Fibonacci или divergence.

`scripts/run_research_cycle.py`: frozen protocol hash guard, строгий CSV,
общий `app.lab.execution.simulate`, одинаковые split/ledgers/risk/cost assumptions,
помесячный учёт и entry-regime attribution. Future strategy может реализовать
тот же интерфейс в новом versioned protocol; автоактивации или plugin hooks нет.
Параметры не обучаются и не выбираются по test. Version2 отражает новые кандидаты;
его A/B/C/D нельзя отождествлять с предыдущим fixed offline experiment.

## 3. Правила, зафиксированные до вычисления новых результатов

[RESEARCH_CYCLE_PROTOCOL.json](RESEARCH_CYCLE_PROTOCOL.json), SHA256
`6eabecd3300e203d5418538be0b71bd2529d6424b71e89a6e10f5e59aa9cf5a3`.

| Кандидат | Entry на closed candle | Strategy exit | Защита |
|---|---|---|---|
| A Donchian ATR | close выше prior20 high LONG / ниже prior20 low SHORT, current bar исключён | противоположный prior10 channel | SL2ATR14 / TP4ATR14 |
| B EMA trend | EMA20>50 и close>EMA20 LONG; inverse SHORT, persistent alignment | EMA reverses или price теряет EMA20 | SL2ATR14 / TP4ATR14 |
| C RSI regime | RSI14 возвращается выше30 LONG / ниже70 SHORT; ADX14≤20 и EMA20/50 spread≤0.5ATR | RSI достигает50 либо ADX≥25 | SL2ATR14 / TP4ATR14 |
| D Aura-indicators alternative | EMA20/50 alignment + RSI≥55/≤45 + MACD histogram sign + volume≥prior20 mean, положительный mean | EMA reverses / RSI теряет50 / MACD histogram меняет знак | SL2ATR14 / TP4ATR14 |

Общие условия: initial10000 USDT, risk budget≤1%, notional≤2000 USDT,
max1 position, virtual collateral1x для LONG/SHORT, fee10bps (0.10%) per side,
adverse slippage5bps (0.05%) per fill. Это model assumptions, не реальные
exchange tariffs или подтверждённые Render settings. Один верхний risk budget
не означает одинаковый фактический stop risk: notional cap часто ограничивает size.

Сигнал на close, fill не раньше next open. Distances известны на signal close
и центрируются на actual fill. Stop-gap adverse, TP-gap capped на target,
both hits→SL; opening protection перед pending strategy exit. Entry bar может
законно достигнуть SL/TP после entry open. Price path внутри OHLC неизвестен.
Сигналы при занятой позиции игнорируются, same-open reversal не добавлен.
Strategy exit тоже next open. Slippage уже включён в prices/PnL, не вычитается
повторно. Money/fees8, quantity floor12, Decimal64. Gap-loss может превысить
planned stop risk. Full mark-to-adverse-liquidation equity включает exit fee.

Development `[2026-05-01,2026-08-01)`, первые500 свечей warm-up: performance
с `2026-05-06 05:00 UTC`, **8332** свечи. Test `[2026-08-01,2026-10-01)`,
**5856** свечей, прошлые8832 для индикаторов, **не полноценный10000 warm-up**.
Test starts flat с новым ledger. Августовские позиции могут перейти в сентябрь;
forced liquidation только на final close сегмента. Default70% в Baseline не
используется: календарные границы фиксированы явно. Final open positions0
от terminal liquidation, не от скрытого удаления позиций; monthly carry сохранён.

## 4. Данные и ограничение многолетней проверки

После смены среды старый `/tmp` CSV и snapshots исчезли. Пользователь повторно
прикрепил файл; он скачан через uploaded-file tool, не Binance API.
Размер2367734 bytes, 14688 закрытых свечей, Binance12 columns, no header,
microsecond timestamps; chronology/OHLCV/close_time/gaps/duplicates проверены
существующим importer. SHA256 снова совпал:
`cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`.
Ни одна price candle не generated/forward-filled. Provenance — заявление
пользователя; независимая проверка подлинности через официальный архив не выполнена.

Ограниченная попытка получить официальный January2023 checksum по
`data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/…zip.CHECKSUM`
вернула `ConnectError`. Additional-permission попытка прервана без результата;
ни ZIP, ни checksum не получены. Proxy/VPN/region bypass и дальнейшие retries
не делались. **Multi-year dataset и независимая multi-year validation NOT RUN**.
Текущий CLI фиксирует этот2026 эксперимент; новые периоды требуют нового
versioned frozen protocol, а не незаметного расширения test range.

## 5. Фактические результаты baseline

### Development

| Кандидат | Входы/закрыто | Win rate | Expectancy USDT | PF | Net PnL USDT | Return | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 381 | 23.3596% | -7.7191 | 0.29009832 | -2940.96468421 | -29.4096% | 29.6195% |
| B | 839 | 16.8057% | -6.3270 | 0.25491717 | -5308.35427930 | -53.0835% | 53.1328% |
| C | 2 | 0% | -11.5979 | 0 | -23.19583944 | -0.2320% | 0.2320% |
| D | 417 | 22.7818% | -6.1272 | 0.29589670 | -2555.04643657 | -25.5505% | 25.7158% |

### Test: август–сентябрь

| Кандидат | LONG/SHORT/WAIT | Входы/закрыто | Win rate | Expectancy | PF | Net PnL | Return | Max DD | Fees |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 306/254/5296 | 248 | 25% | -5.7417 | 0.38074397 | -1423.94215025 | -14.2394% | 14.2450% | 992.04681736 |
| B | 2138/1778/1940 | 547 | 15.1737% | -5.9866 | 0.25240544 | -3274.67364075 | -32.7467% | 32.7652% | 2188.27671301 |
| C | 2/1/5853 | 3 | 0% | -11.1037 | 0 | -33.31121630 | -0.3331% | 0.3331% | 11.99236525 |
| D | 597/465/4794 | 282 | 21.2766% | -5.4716 | 0.31665041 | -1542.98444404 | -15.4298% | 15.4298% | 1128.07440057 |

Final balance/equity: A8576.05784975, B6725.32635925, C9966.68878370,
D8457.01555596. Candidate signals не равны entries из-за занятой позиции,
next-open availability и gates. `TARGET_AFTER_COSTS` rejects A32/B168/D43,
C0: net target reward не положителен после издержек. Нет скрытой подмены
WAIT техническими errors. Большое число B-сделок — persistent trend mode,
не EMA crossover-only из предыдущего исследования.

Control buy-hold cap2000: одна LONG, +652.13552412 USDT (+6.5214%), DD1.9116%,
fees4.65679232. Classic budget10000: +3257.42020045 (+32.5742%), DD7.8033%,
fees23.26070089. У benchmark нет SL, 1% stop-risk constraint и сравнимой
экспозиции; win rate100%/one trade не подтверждает edge, PF без losses null.
В development оба passive варианта отрицательны (−458.6249 / −2290.8335 USDT).

Historical Pattern: **reuse ранее реально выполненного production replay** из
`docs/FIXED_STRATEGY_RESULTS.json`, не новый запуск этой задачи. Исходный CSV,
source SHA всех native файлов, default PatternConfig и warm-up/период совпали;
reference JSON hash записан. 8332 development WAIT, 5856 test WAIT,0 trades,
PnL/DD0, win rate/expectancy/PF undefined. Он сохраняет native close-fill без
slippage и без terminal force-close, поэтому **unranked, not common-engine equivalent**.
Ничего не изменено ради искусственного сравнения или роста числа сигналов.

## 6. Помесячные результаты, режимы и sensitivity

Monthly closed PnL включает обе fees сделки в месяце exit. Отдельные cashflow
PnL/balance change учитывают entry fee по entry month, поэтому отличаются
при carry. Equity change учитывает unrealized/estimated liquidation costs.
Обе monthly суммы сверены; global drawdown вычислен по полным curves.

| Кандидат | Август closed PnL / closed trades | Сентябрь closed PnL / closed trades |
|---|---:|---:|
| A | -584.07893710 / 125 | -839.86321315 / 123 |
| B | -1613.99818243 / 267 | -1660.67545832 / 280 |
| C | -10.84888783 / 1 | -22.46232847 / 2 |
| D | -573.22824547 / 133 | -969.75619857 / 149 |

Полные May/June/July/August/September monthly fees, win rate/PF, cashflow,
equity/drawdown и balances находятся в JSON. A переносит1 позицию на границе
август/сентябрь; B/C/D не переносят. Curve содержит каждый закрытый15m tick
с полной mark-to-market оценкой, не chart/UI limit500.

### Зафиксированная cost sensitivity (не optimizer)

| Кандидат | Lower assumption fee5/slip2bps | Baseline fee10/slip5bps | Stress fee20/slip10bps |
|---|---:|---:|---:|
| A | -655.8380 / 264 trades | -1423.9422 / 248 | -2684.8090 / 222 |
| B | -1597.6401 / 581 | -3274.6736 / 547 | -5569.4243 / 468 |
| C | -19.7912 / 3 | -33.3112 / 3 | -35.4414 / 2 |
| D | -757.4319 / 304 | -1542.9844 / 282 | -2945.9648 / 252 |

Это реальные отдельные исторические прогоны с fixed signals и другими
заранее объявленными costs; sizing/target gates поэтому могут менять entries.
Даже lower-assumption варианты отрицательны. Costs не подобраны ради выигрыша.
Low-cost assumptions не утверждаются доступными на реальной бирже.

Regime labels берутся из ADX на **entry signal**, не из будущего режима.
В test RANGE/TRANSITION/TREND net PnL: A −646.04/−321.19/−456.71,
B −1821.71/−429.01/−1023.95, D −732.37/−262.26/−548.36 USDT.
C имеет3 RANGE trades, −33.31. Это attribution, не independently reinitialized
regime backtests. Нет наблюдаемого прибыльного bucket для A/B/D; отбор
post-hoc «удачного режима» не выполнялся. C на малой выборке нельзя объявлять
победителем за малый drawdown — он почти не принимает экспозицию.

## 7. Независимые проверки, ошибки и ограничения проверки

`scripts/audit_research_report.py` повторил полный отчёт с exact equality и
проверил **2723** baseline/control trades: рациональные adverse fills,
независимые Decimal fees/PnL, CSV entry/exit prices, risk≤budget, notional≤2000,
balance, peak-to-trough DD и monthly cashflow/balance sums. PASS.
17 новых стандартных unittest tests PASS: future perturbation A/B/C/D,
EMA/RSI/MACD/volume gates, frozen registry, Donchian current-bar exclusion,
ATR oracle, next-open/pre-entry OHLC, ambiguous SL/TP, gap, LONG/SHORT
profit/loss Fraction oracle, Decimal context, split/reproducibility, bad CSV,
missing-file honest null metrics, source guard и no-exchange dependency.

Найденные diagnostic defects исправлены с regression tests:

1. Serialized JSON horizons list сравнивался с Pydantic tuple: ложный reference
   mismatch. Теперь сравнение canonical JSON, source mismatch по-прежнему блокируется.
2. Monthly carry исключал позицию с next-open exit ровно на boundary. Теперь
   различаются close-exit в заканчивающейся свече и pending next-open exit;
   это исправление отчётности, не стратегии/исполнения.

Все **101 JavaScript tests PASS**, JS syntax PASS. Все87 Python sources AST
parsed, `app.main` import PASS. Статический review новых файлов/private-client
dependencies и heuristic secret scan PASS. Existing production files unchanged.
**Full legacy pytest suite NOT RUN**: `python -m pytest -q` попытка вернула
`No module named pytest`; прежний временный pytest package исчез после смены
среды. Предыдущие748 pass относятся к прошлой задаче и не выдаются за текущий run.
Новые unittest tests также discoverable by pytest, когда он доступен.
Optional ruff/mypy/bandit/coverage, live Render/mobile/accounts NOT RUN.

Architecture/security passes: strategy interface принимает только bars,
общий execution не дублируется, private clients/credentials/activation не
инжектируются, все outputs отдельные research files. Внешний CSV не содержит
исполняемых инструкций; чтение data не предоставляет authority для торговли.
Real-money execution disabled, Auto/UI/account/risk/live-data код не изменён.

## Воспроизводимость и доставка

```bash
python -B scripts/run_research_cycle.py /path/to/BTCUSDT-15m-2026-05_to_09.csv \
  --max-seconds 180 --output /tmp/aura-research-cycle.json
python -B scripts/audit_research_report.py /path/to/BTCUSDT-15m-2026-05_to_09.csv \
  /tmp/aura-research-cycle.json
python -B -m unittest discover -s tests -p test_research_cycle.py -v
```

Output должен быть новым. Если CSV отсутствует, CLI возвращает code2 и
`BLOCKED_HISTORY`, **null**, а не fake zero profits. Input guard16MiB/20000 rows
сохранён; current standalone budget180s, cap600s. Нет web job, новых UI/routes,
SQLite runtime writes, paid services или dependency changes. Native reference
проверяется по source hashes; при изменении native code старый replay не
принимается как актуальный. Baseline trades/curves полные; sensitivity rows
summary-only для ограниченного размера, повторяемые CLI пересчитает те же models.

[RESEARCH_CYCLE_RESULTS.json](RESEARCH_CYCLE_RESULTS.json): parameters, versions,
source/code/protocol hashes, full trades/curves, monthly, regimes, sensitivity,
native control provenance и ограничения. JSON SHA256:
`ad78010443829533570fa8e6c2570c7c96cee8ed72438c0365ec05532c09d7c6`.

## Что делать дальше

Ни один активный кандидат не показал положительного test PnL/expectancy после
costs. Подтверждённого независимого edge нет. Следующий исследовательский цикл:
верифицированные multi-year архивы и отдельный ранее не просмотренный период;
заранее сформулированная гипотеза с меньшим turnover/более длинным horizon,
например1h/4h, и fixed robustness/cost checks. Это предложение для нового
протокола, не изменение нынешних порогов под август/сентябрь. До такой проверки
нет основания подключать этих кандидатов к Auto Paper или реальному исполнению.

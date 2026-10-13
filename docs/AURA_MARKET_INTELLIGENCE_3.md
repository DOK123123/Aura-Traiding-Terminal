# AURA Market Intelligence 3.0 — context-aware offline research

Работа изолирована от production: Auto Paper, авторизация, risk settings, Render UI, обычные paper-портфели и действующий Intelligence Replay не изменены. Никаких реальных ордеров, private exchange clients, API credentials, автоматической активации или сетевой загрузки истории.

## Архитектура и повторное использование

- `research/market_intelligence/structure.py`: причинный market structure и MTF state; подтверждённый pivot и FVG через существующий `app.intelligence.patterns.detect`, EMA/RSI/ATR/ADX через `app.lab.indicators`.
- `strategies.py`: шесть формальных исследовательских setup/entry/invalidation правил, WAIT.
- `similarity.py`: past-fit нормализация, завершённые исторические аналоги, purging, uncertainty и research router; `explain()` всегда read-only/WAIT без production approval.
- `pipeline.py`: фиксированный протокол, labels, streams; финансовый портфель использует **неизменённые** `app.lab.execution.simulate` и `scripts.run_six_year.period_job`, включая независимую Fraction/Decimal проверку accounting каждого закрытия.
- `scripts/run_market_intelligence.py`: explicit CLI, hash-addressed deterministic gzip snapshots/labels/streams/portfolios, checkpoint/resume.

Новый пакет не импортируется веб-приложением. Read-only interface представлен Python-функцией `explain()` и сохранённым историческим JSON-примером. UI/API wiring намеренно не добавлено: исследовательский архив/index на Render не предполагается, provenance/forward validation должны быть проверены перед будущей интеграцией. Это не имитация работающего live-экрана. SHORT — виртуальная signed-price модель на Spot OHLCV; borrow/funding/liquidation economics, bid-ask spread и реальный latency не моделируются. Даже положительная историческая evidence не даёт функции explain разрешение на сделку; будущее paper-исполнение потребует существующей owner-защиты и отдельного ручного подтверждения.

## Операционные определения структуры

Версия `CONTEXT_VECTOR_1.1`, symbol BTCUSDT, основная свеча15m, закрытые UTC1h/4h для контекста.

- Swing: строго выше/ниже двух соседей слева и двух справа. Pivot time хранится отдельно; confirmation time — закрытие второй правой свечи. Текущая свеча не подтверждает будущий pivot.
- HH/LH и HL/LL: сравнение двух последних подтверждённых high/low; изменения ≤0.25 текущего ATR14 — equal. UNKNOWN не выдаётся за равенство.
- Trend: EMA20/50 направление, ADX14 сила; отдельные HH/HL/LH/LL структурные признаки.
- Zones: максимум32 последних подтверждённых pivot каждого типа, price clustering в пределах0.25ATR; ближайшие support≤close/resistance≥close. При отсутствии подходящего pivot применяется **явно отмеченный** prior50 rolling-extrema fallback, не фиктивный confirmed pivot.
- Breakout: close пересекает prior confirmed high/low либо явно обозначенный prior20 fallback на0.1ATR; предыдущий close ещё не был за уровнем.
- Failed breakout: за1..8 следующих закрытых свечей close возвращается за сломанный уровень в противоположную сторону на0.1ATR.
- Retest: за1..8 свечей, после breakout; wick touch level±0.25ATR и направленная body/close снова за0.1ATR. Только одно подтверждение ретеста данного breakout.
- Liquidity sweep: wick за prior уровень на0.1ATR, close вернулся внутрь. Если обе стороны — AMBIGUOUS, направления не изобретаются.
- BOS: close break **подтверждённого pivot**; CHoCH — такой break против прежней HH+HL/LH+LL структуры. Rolling breakout не маркируется BOS. Терминология SMC экспериментальна, не свидетельствует об институциональных действиях.
- FVG: существующий трёхсвечный non-overlap, подтверждённый закрытием третьей свечи; полное заполнение или64 свечи снимает активную область.
- Order block: последняя opposing-body свеча среди предыдущих восьми при подтверждённом BOS/CHoCH; body zone, origin time отдельно от confirmation; invalidated close через дальнюю границу либо expiry16 свечей. Это операционная модель, не обнаружение реального биржевого ордера.
- Volatility: ATR14/close относительно медианы предыдущих64 — expansion≥1.5/compression≤0.65.
- Volume confirmation: volume / prior20 mean≥1.5; отсутствующая/нулевая база не становится подтверждением.
- Range: ADX≤20 и prior50 high-low width≤6ATR. Position inside range может выйти за0..1 при breakout, не скрывается.
- Pullback: distance от prior20 extreme в EMA-направлении, в ATR; support/resistance distances также в ATR. Momentum: RSI14 и EMA12−EMA26/ATR (MACD-line, не MACD signal crossover).
- MTF: только полный UTC block из4/16 реальных15m; последняя **закрытая** старшая свеча, её time≤analysis cutoff; после разрыва новый прогрев, старое состояние за gap не переиспользуется.

21 измерение: trend, ADX strength, ATR/close, relative volume, range position, distances to levels, liquidity direction, RSI, MACD/ATR, pullback, high/low leg, structural-known mask, BOS/CHoCH direction, FVG/OB side, range flag,1h/4h directions и MTF-known mask. Unknown masks сохраняются. Коррелированные признаки распределены по семи семействам расстояния и не суммируются как независимые подтверждения. Ambiguous sweep не получает направленный голос.

## История, причинность и нормализация

Использован локальный предоставленный архив2020–2025. SHA256/CHECKSUM/CRC/manifest,12 колонок, OHLCV, chronological order и timestamp units проверяются существующим `load_years`. Ожидаемый census проверяется, не подгоняется:210280 raw,152 отсутствующих,8 quarantined invalid close_time,210272 usable,160 unavailable,16 effective gaps и27 первоначальных аннотаций. Внутренняя согласованность CHECKSUM не заменяет независимую аутентификацию официальным сервером; повторной сетевой загрузки нет.

**2025 исключён до вычисления новых states/outcomes**: он уже изучался, не новый blind holdout. Development archive2020–2022:2020Q1 только calibration/аналоговая история; performance начинается2020-04-01. Validation2023–2024 — временная проверка новой фиксированной конфигурации, но рынок этих лет уже многократно просмотрен в прежних исследованиях. Новый forward-период нужен для независимого подтверждения.

Нормализация mean/std fit исключительно2020Q1 closed states, scale floor0.1; после2020-04-01 она заморожена. Z-values clip±5, group weights fixed. Никакой fit по validation/2025. Слабая репрезентативность Covid-квартала и clipping при distribution shift — ограничения данного фиксированного baseline, не причина подбирать параметры на validation.

После gap контекст и higher TF сбрасываются,250 собственных свечей на features; существующий segmented execution требует1000 новых15m свечей. Данные не заполняются. Открытая позиция на gap не получает выдуманный exit: её исход неизвестен; условный ledger закрытых известных сделок восстанавливает entry fee и исключает её exposure. Любой censored/halting период не проходит отбор. В нормальных известных period boundaries ликвидация по наблюдаемому close. Conditional PnL и gap drawdown lower bound явно маркируются.

## Исторические аналоги и router

Фиксированная выборка setup-events на **том же** segment-index grid i%16==0 после1000-bar execution warmup. Никакого offset между обучающими event anchors и исполняемыми сигналами. Label использует существующий Decimal engine: initial signal at close, fill next open, protective/invalidation/time exit только на последующей реальной истории. Неизвестные исходы gaps не получают labels; cost/risk refusal учитывается отдельно от missing data.

Каждый label имеет entry-signal timestamp, resolved_at, direction/family, vector, regime, masks, stop policy и exit scope. При query allowed только resolved_at<query close и event timestamp минимум четырьмя днями раньше. Pairwise purge4 days; outcomes не пересекаются. Это не делает long-memory MTF/EMA context независимым: остаётся temporal dependence.

Reference memory растёт причинно: для позднего2024 query разрешены уже resolved outcomes раннего2023/2024, без изменения параметров. Это **prequential online evaluation**, не frozen-training-bank OOS. Использование будущих outcomes запрещено, но такая адаптивная validation отличается от полностью замороженного train-only банка; это не скрывается как blind test.

Similarity: RMS standardized Euclidean с одинаковым весом семи семейств: trend/structure, volatility, volume, range/levels, liquidity/SMC, momentum/pullback, MTF. Exact filters family, side, regime, structural mask, MTF mask и volume availability. Последние2048 завершённых labels данного bank, distance≤1.5, максимум64 neighbors. Small/bounded pool не означает отсутствие всех аналогов во всей мировой истории.

Evidence: count, win/loss, TP-first frequency, net expectancy after costs, PF, positive14-day-block fraction, descriptive chronological sample drawdown. Lower95 — приблизительный normal interval средних14-day blocks, ≥8 blocks. Это не калиброванная вероятность будущей сделки. Определение threshold не оптимизируется по исходу.

Режимы:

- RULE: фиксированная priority шести setup правил; исследовательский baseline без edge-claim.
- NEAREST: ≥30 аналогов, smallest mean distance; baseline, не обязательное положительное ожидание.
- EDGE: ≥30, ≥8 blocks, lower95>0, PF≥1.1, positive-block fraction≥2/3. Затем отдельная проверка итогового development/validation портфеля; никакого production approval.

WAIT различает no context setup, calibration, недостаток аналогов и NO_EDGE. Для исследовательского ALL router единая exit model protective SL/TP плюс UTC daily time exit, без смены invalidation при новом выбранном семействе. Его analog banks имеют точно такую же UNIVERSAL exit model. Отдельные family hypotheses используют собственную invalidation.

## Шесть фиксированных стратегий

| ID | Entry | Invalidation на следующем open |
|---|---|---|
| BREAKOUT_CONTINUATION | новый breakout в EMA направлении, ADX≥25, volume≥1.5 | смена EMA направления или failed break против позиции |
| FAILED_BREAKOUT_REVERSAL | подтверждённый failed breakout, противоположное направление | новый breakout против позиции |
| BREAKOUT_RETEST | подтверждённый более поздний retest | EMA перестал совпадать либо failed break |
| TREND_PULLBACK | ADX≥25, full MTF alignment, depth0.5..2ATR, directional body | потеря MTF agreement/EMA направления |
| RANGE_MEAN_REVERSION | range, position≤.15+RSI≤40 LONG;≥.85+RSI≥60 SHORT | возврат к midpoint либо потеря range |
| VOLATILITY_EXPANSION | volatility≥1.5, volume≥1.5, breakout в EMA направлении | EMA direction/failed break |

Защитные варианты заранее фиксированы: distance SL2%/TP4% **из известного signal close** либо2ATR/4ATR; реальные уровни от actual next-open adverse fill. Поэтому после гэпа это не строго2% от нового fill. UTC midnight closed candle schedules следующий open exit, максимум24h; это ограничение, не фиксированный срок каждой сделки. Protective gap exit имеет приоритет, TP gap без оптимистичного улучшения, ambiguous SL+TP — SL first.

Capital10000 USDT отдельно каждый период, planned fee-inclusive risk≤1%, cap2000 USDT, максимум одна позиция. Fee10bps/side, adverse slip5bps/fill; stress20/10 с **тем же baseline-cost signal stream**, без повторного обучения/выбора. Gap loss может превышать planned1%: не гарантируем максимальный реализованный убыток.

## Бюджет, отбор и контроли

6 families+ALL ×3 modes ×2 stop policies =42 hypotheses. Все42 тестируются на обеих фазах baseline/stress;168 основных portfolios. Validation всех фиксированных конфигураций описательная; только одновременно прошедшие заранее определённые development и validation gates могут стать RESEARCH_CANDIDATE.

Gates: ≥100 development/≥60 validation trades; positive net в каждом календарном годе (2020 performance partial), DD≤25%, positive stress, отсутствие censored positions/balance halt. Portfolio block bootstrap14 days/19999 reps, seed20261013. Known comparison-family floor869=810 prior patterns+42 new+17 prior Lab versions; Bonferroni .05/869, lower95 daily-PnL positive. История более раннего подбора не исчерпывающе учтена, stationary/block assumptions приблизительны: поэтому даже проход не означает подтверждённо прибыльную live-систему.

No-trade=0; существующие DONCHIAN/EMA_RSI_ADX signal functions с общей защитной/expiry model; five random seeds, частота оценена только на development и затем фиксирована для validation (в development это frequency-conditioned baseline). Random не получает future validation frequency.14 контрольных portfolios считаются при normal costs; doubling-cost stress относится к168 основной матрице, не к этим controls. Прежние Pattern Research810 и Lab17 — неизменённые reference-отчёты: разные warmup/expiry/features, нельзя объявлять прямое rank superiority.

Router decision-audit counters относятся ко всему2020–2024 dataset, включая calibration, и повторяются как общий descriptor при разных phases; не суммировать их повторно. Engine rejections, signals и financial metrics каждого period — отдельные. Суммы независимых симуляций и повторных outcome labels не являются числом независимых рыночных наблюдений.

## Запуск

```bash
python -B scripts/run_market_intelligence.py /path/AURA_BTCUSDT_15m_2020-2025.zip \
  --output /tmp/aura-market3 --report docs/AURA_MARKET_INTELLIGENCE_3.json
python -B scripts/audit_market_intelligence.py /tmp/aura-market3
python -B scripts/report_market_intelligence.py --output /tmp/aura-market3 \
  --report docs/AURA_MARKET_INTELLIGENCE_3.json --markdown docs/AURA_MARKET_INTELLIGENCE_3.md
python -B -m unittest tests.test_market_intelligence -v
```

Повтор той же команды resume с проверкой полного source/parameter/archive signature и SHA snapshots/streams/ledger. Изменённые параметры/код не смешиваются с предыдущими результатами. `--seconds`, `--job-seconds` и `--max-jobs` задают budget; job execution deadline проверяет существующий engine, prepare bounded размером ≤211000 source bars, bank≤100000 labels, search42. Одна исследовательская команда на output directory. Gzip mtime0/canonical JSON; source version и нормализатор сохраняются.

Наблюдаемый RSS около1.2GB: требуется workstation/cloud research с запасом RAM, рекомендуется≥2GB. **Не запускать runner на Render Free.** Raw source archive, большие state/label snapshots, journals и curves не коммитятся. Приложение продолжает использовать прежние runtime-файлы. Зависимости не добавлялись; установленная sandbox-среда отличается от requirements, полная Render validation не заявляется.

## Review

Отдельные проходы architecture, Python, security, causality, market structure, trading math и reliability/testing. Исправления до окончательного прогона: BOS только confirmed-pivot, сбор подтверждённых pivot при прогреве, включение структурных/SMC/missing-mask признаков в vector, одинаковая фаза event-label/query grids, отделение cost refusal от unresolved gap, validation входных normalizer/router параметров. Никакой коррекции ради повышения прибыли.

Фактические результаты и проверки добавляются после завершения прогона.

## Фактический завершённый результат

**NO_EDGE_FOUND**. Source protocol SHA256 `a0ad02c27238a4fb9d17830c08e443af30fa92fa3cf91bdc72b5fa9f086951c1`.
Закрытых причинных состояний: 170999; source candles2020–2024: 175232. Label statistics: `{'completed_labels': 6403, 'label_rejected:TARGET_AFTER_COSTS': 10, 'sampled_states': 9965, 'setups': 1605, 'unresolved_gap_labels': 7}`.
Проверены шесть стратегий+общий router,42 конфигурации,84 phase-results baseline/stress. Всего completed portfolios: 182, кандидат одновременно development+validation: 0.
Classes всех phase-results: `{'INSUFFICIENT_EVIDENCE': 46, 'REJECTED': 38}`. Ни RULE, ни NEAREST baseline не активируется. 2025 не использован для новой trading performance.

| ID | Development net USDT | Validation net USDT | Trades dev/val | Stress val | Class dev/val |
|---|---:|---:|---:|---:|---|
| VOLATILITY_EXPANSION:RULE:ATR_2_4 | 243.17897605 | -131.39971678 | 15/23 | -272.16168692 | INSUFFICIENT_EVIDENCE/REJECTED |
| BREAKOUT_CONTINUATION:RULE:ATR_2_4 | 174.77901444 | -204.46572327 | 47/51 | -480.03260023 | REJECTED/REJECTED |
| VOLATILITY_EXPANSION:RULE:PCT_2_4 | 0.47910007 | -85.29100951 | 15/23 | -221.04899128 | INSUFFICIENT_EVIDENCE/REJECTED |
| BREAKOUT_CONTINUATION:NEAREST:PCT_2_4 | 0 | 0 | 0/0 | 0 | INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE |
| BREAKOUT_CONTINUATION:NEAREST:ATR_2_4 | 0 | 0 | 0/0 | 0 | INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE |
| BREAKOUT_CONTINUATION:EDGE:PCT_2_4 | 0 | 0 | 0/0 | 0 | INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE |
| BREAKOUT_CONTINUATION:EDGE:ATR_2_4 | 0 | 0 | 0/0 | 0 | INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE |
| FAILED_BREAKOUT_REVERSAL:NEAREST:PCT_2_4 | 0 | -342.85007623 | 0/42 | -594.35583758 | INSUFFICIENT_EVIDENCE/REJECTED |
| FAILED_BREAKOUT_REVERSAL:NEAREST:ATR_2_4 | 0 | -295.92902244 | 0/40 | -541.08035690 | INSUFFICIENT_EVIDENCE/REJECTED |
| FAILED_BREAKOUT_REVERSAL:EDGE:PCT_2_4 | 0 | 0 | 0/0 | 0 | INSUFFICIENT_EVIDENCE/INSUFFICIENT_EVIDENCE |

### Ненулевые лучшие numerical результаты, не победители

development: `VOLATILITY_EXPANSION:RULE:ATR_2_4`, net 243.17897605 USDT, trades 15, class INSUFFICIENT_EVIDENCE, reasons `['TOO_FEW_TRADES', 'YEAR_UNSTABLE', 'MULTIPLE_SEARCH_UNCERTAINTY', 'BLOCK_CI_NONPOSITIVE']`.
validation: `BREAKOUT_RETEST:NEAREST:PCT_2_4`, net -14.58309367 USDT, trades 10, class REJECTED, reasons `['NET_NONPOSITIVE']`.

EDGE router configurations: 28 phase-results; actual closed trades sum 0. Повторные симуляции не независимые наблюдения.

**ПОДТВЕРЖДЁННОГО ПРЕИМУЩЕСТВА НЕТ.** WAIT является корректным результатом. Ноль сделок/мало аналогов — недостаток evidence, а не доказательство отрицательной доходности каждого возможного setup.

### Результаты по годам и ограничения

State census: `{'2020': {'closed_states': 32810, 'pivot_confirmations': 9349, 'known_mtf': 13947, 'breakout': 2847, 'liquidity_sweep': 4259, 'failed_breakout': 1728, 'retest': 1266}, '2021': {'closed_states': 33228, 'pivot_confirmations': 9149, 'known_mtf': 12177, 'breakout': 3062, 'retest': 1425, 'failed_breakout': 1804, 'liquidity_sweep': 4267}, '2022': {'closed_states': 35040, 'pivot_confirmations': 9780, 'known_mtf': 31777, 'breakout': 2886, 'retest': 1439, 'liquidity_sweep': 4362, 'failed_breakout': 1692}, '2023': {'closed_states': 34785, 'pivot_confirmations': 9604, 'known_mtf': 31027, 'liquidity_sweep': 4290, 'breakout': 3066, 'failed_breakout': 1834, 'retest': 1379}, '2024': {'closed_states': 35136, 'pivot_confirmations': 9384, 'known_mtf': 35136, 'breakout': 3125, 'failed_breakout': 1872, 'liquidity_sweep': 4052, 'retest': 1470}}`.
Financial yearly/monthly metrics, Long/Short, regimes, gross/net,fees/slippage/turnover,DD,expectancy иbootstrap находятся в JSON для каждого portfolio. Полные journals/curves — внешние gzip artifacts сSHA в каждом результате; пересоздаются CLI, не публикуются как миллионы строк.
Clipping: `{'evaluated_states': 163296, 'clipped_counts': {'volume': 1399, 'structure_event': 3058, 'support_distance': 1145, 'resistance_distance': 836, 'h4': 124064, 'range_position': 49, 'pullback': 87, 'volatility': 18}, 'note': 'Descriptive clipping counts with frozen2020Q1 scaler; no refit to improve validation.'}`.
Calibration availability: `{'states': 7703, 'h1_available': 4704, 'h4_available': 0}`.
В2020Q1 после gap/warmup не было доступных250-bar4h состояний: h4 mean0, scale floor0.1. Поэтому124064 последующих h4 значений clip в+-5. Это существенное ограничение metric/calibration, не основание менять параметры после просмотраvalidation. Следующий заранее фиксированный исследовательский протокол должен отдельно проверить categorical encoding и expanding past-only calibration на development folds.
Per-period signal и risk refusals видны в financial results; decision_audit — общий counter source dataset, не сумма независимых observations. Label cost rejections отделены от unknown gap outcomes.
Independent audit: `{'closed_trades_checked': 20794, 'errors': 0, 'jobs_checked': 182, 'method': 'Independent Fraction adverse-fill verification, Decimal commission/PnL/risk, next-open, SL/TP/gap touches, one-position overlap, cash reconstruction, mark-to-market equity and drawdown. Conditional gap outcomes are not asserted investable.'}`.
Checks: `{'python_unittest_passed': 156, 'javascript_passed': 106, 'failures': 0, 'new_tests': 31, 'python_syntax_files': 120, 'app_main_import': 'PASS', 'static_security_findings': [], 'full_pytest': 'NOT RUN: No module named pytest; unexecuted case count not enumerated', 'render_android': 'NOT RUN / unchanged', 'requirements_changed': False, 'environment': 'Python3.12.14; FastAPI0.141.1; httpx0.28.1; NumPy2.3.5; differs from requirements', 'reviews': ['architecture', 'Python', 'security', 'market structure', 'causality', 'trading math', 'reliability/testing'], 'actual_resume_report_identical': True, 'resume_full_report_sha256': '42dde5f6d36eef9feebe765ba5188bb9617133ae3d9b7b67f1702f8912301cf4'}`.
Рекомендация: новый заранее зафиксированный forward dataset, проверка calibration robustness только на past development folds и минимального числа механизмов; не ослаблять thresholds после просмотраvalidation. Нативный интерфейс/owner-подтверждение и execution остаются прежними. Никаких автоматических включений.
Фактический Render/Android/live UI test NOT RUN; среда установленных dependencies отличается от requirements, полный pytest недоступен.

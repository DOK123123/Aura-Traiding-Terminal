# AURA Pattern Research 2.0 — протокол и результаты

Офлайн-исследование BTCUSDT по реальному предоставленному архиву. Production, Auto Paper, live execution, owner authentication, интерфейс Render и Intelligence Replay не изменяются. Никаких биржевых ордеров, credentials, сетевой загрузки или автоматической активации.

## Протокол, зафиксированный до расчёта

Реестр и детекторы переиспользуются напрямую из `app/intelligence/patterns.py`: 21 IMPLEMENTED и 9 EXPERIMENTAL, версия 1.0. 43 PLANNED не обнаруживаются и не входят в сетку. Определения — детерминированные исследовательские правила, а не утверждение, что они совпадают со всеми учебниками технического анализа.

Разбиение: development 2020–2022; validation 2023–2024; повторная проверка 2025 только после lock финалистов. **2025 уже изучался в AURA_SIX_YEAR_BACKTEST: это не новый untouched/blind holdout.** Статусы HOLDOUT_PASSED и PAPER_ONLY_ELIGIBLE намеренно недоступны на этой истории. Нужен новый заранее отложенный forward-период.

Сетка: 30 паттернов × три таймфрейма × (восемь контекстов с SL2%/TP4% + один вариант без дополнительного контекста SL2ATR/TP4ATR) = **810 гипотез**. ATR14, текущий close для процентов; stop/target distance известны при закрытии сигнальной свечи, уровни привязываются к фактическому следующему entry fill. Нет подбора после просмотра результатов. Neutral-модели требуют направление причинной EMA20/50; это явно отдельная гипотеза о направлении, а не прогноз Doji/Inside Bar сам по себе. LONG/SHORT и расходы сохраняются раздельно в JSON.

Контексты:

- NONE — только детектор; нейтральный детектор получает направление EMA20/50.
- TREND — направление согласовано с EMA20/50, ADX14 ≥25.
- VOL_HIGH / VOL_LOW — ATR/close относительно медианы предыдущих 64 наблюдений ≥1.5 / ≤0.65.
- VOLUME — текущий объём / средний предыдущих 20 ≥1.5.
- SR — LONG: close ≤ минимум предыдущих 50 low + ATR; SHORT: close ≥ максимум предыдущих 50 high − ATR. Это односторонняя зона, включая пробой за уровень, а не абсолютное расстояние.
- INDICATORS — TREND плюс RSI14 50–70 LONG /30–50 SHORT.
- TREND_VOLUME — два контекстных семейства одновременно.

Коррелированные модели не суммируются как независимые подтверждения. В одной гипотезе один детектор и максимум два контекстных семейства. Регимы, direction, volatility, RSI, ADX и volume вычисляются из того же закрытого префикса 250 свечей, что и действующий Intelligence; не заменены пересчитанными глобальными EMA.

Начальный независимый баланс каждого периода 10000 USDT; плановый fee-inclusive риск ≤1%; max notional2000 USDT; максимум одна позиция. Комиссия10bps/сторону, adverse slippage5bps/fill; stress20/10bps. Это условия исследования, не настройки Render и не заявленный тариф биржи. В гэпе фактический убыток может превышать плановый риск стопа.

Сигнал только на закрытии, исполнение — не раньше следующего open. Используется неизменённый `app.lab.execution.simulate`: Decimal деньги/quantity/PnL; adverse stop gap, благоприятный TP gap без улучшения цены, при касании SL и TP — SL первым. Общий time exit: следующая open после закрытой свечи, заканчивающейся на UTC границе четырёх суток от Unix epoch. Это **максимальный**, а не фиксированный срок удержания; может быть меньше четырёх суток. В конце известного периода ликвидация по наблюдаемому close, последняя сигнальная свеча не открывает позицию задним числом.

## Данные и разрывы

Архив `AURA_BTCUSDT_15m_2020-2025.zip`, SHA256 `61eeafddd5fd7d955a149030d08075959a47e4f66171c0f3fe0d6c08d496c50d`. Существующий `load_years(...allow_gaps=True)` сверяет ZIP/CHECKSUM/manifest/CRC, реальные OHLCV, интервалы и timestamp units. Ожидаемые числа проверяются, расхождение вызывает отказ, а не исправление данных: 210280 raw, 152 действительно отсутствующих, восемь карантинных close_time, 210272 пригодных, 160 недоступных, 16 разрывов, 27 исходных замечаний. Месячные замечания не повторно считаются пропущенными свечами. Полная геометрия разрывов в JSON data_quality.

SHA/CHECKSUM согласованы внутри предоставленного набора. В этой задаче не выполнялась независимая загрузка контрольных сумм с официального сервера: аутентичность происхождения не доказана одной внутренней согласованностью.

1h/4h собираются исключительно из полных UTC блоков 4/16 реальных15m свечей. После каждого эффективного разрыва индикаторы сбрасываются, требуется новый прогрев250 свечей своего TF; неполный блок отсутствует. Никакого forward-fill, придуманных цен или подтверждения pivot будущими незавершёнными свечами.

Открытая позиция на разрыве остаётся с неизвестным результатом, не закрывается выдуманной ценой. Для описательного сравнения известных закрытых сделок её entry fee восстанавливается в **условном censored ledger**, её экспозиция исключается из соответствующего участка equity. Это не инвестируемая доходность полного периода. Любой такой период не проходит отбор. Censored positions и размер выборки видны в JSON. Отсутствующая свеча также не исполняет pending entry.

## Статистика и критерии

Development: ≥100 сделок, положительный net во всех трёх календарных годах (год без сделок не проходит), DD≤25%, положительный stress и отсутствие цензурирования. Validation: ≥60 сделок, оба года положительны, те же рисковые/стресс-условия. Максимум10 финалистов, manifest/hash фиксируется до их проверки2025.

Блочный circular bootstrap дневного portfolio PnL, фиксированный seed20261013, блок14 дней, **19999 повторов**. Учитываются связанные доходы внутри блока, не используется iid bootstrap отдельных сделок. Нижняя граница95% и центрированная односторонняя bootstrap p приблизительны; требуют стационарности и достаточной длины зависимости. Для всего семейства применяется Bonferroni .05/810, включая неудачные попытки. Разрешение минимальной p=1/20000 позволяет пройти порог, не гарантируя прохождение. Дополнительная чувствительность блоков14/28/56 дней не используется для нового отбора. Нельзя объявлять «доказанную вероятность прибыли» по этой оценке.

Sharpe — существующая метрика движка: полные UTC daily liquidation-equity returns, sample stdev, sqrt365, zero risk-free; undefined при <20 trades/<30 daily returns/zero variance/nonpositive equity. Equity и drawdown censored ledger условны. PF undefined при отсутствии потерь; win rate/expectancy undefined без сделок, не заменяются искусственными нулями/бесконечностью.

Top10 numerical development дополнительно прогоняются на validation для диагностики, **даже если не прошли статистические gates**; EXPLORATORY_NOT_ELIGIBLE не может стать финалистом. Полный перечень810 попыток, rejections, direction/regime/year/month attribution, fees/slippage/turnover, equity и journal хранятся в checkpoints/JSON. Gross filled PnL уже включает slippage; gross raw path и slippage вынесены отдельно, нельзя вычитать slippage повторно.

Классы: при нуле сделок — INSUFFICIENT_EVIDENCE/NO_TRADES; REJECTED при nonpositive net наблюдаемых сделок или unresolved gap; INSUFFICIENT_EVIDENCE при нехватке выборки/неустойчивости/стрессе/неопределённости; RESEARCH_CANDIDATE только после всех gates. NO_EDGE_FOUND означает отсутствие прошедших критерии в этой конечной сетке, не математическое доказательство отсутствия любых рыночных закономерностей.

## Контрольные сравнения

Отдельный заранее фиксированный control manifest: no-trade; существующие DONCHIAN/EMA_RSI_ADX сигнал-функции с общими защитными выходами; пять random seeds с сопоставимым числом сигналов на каждом сегменте и случайным направлением. Random comparator обусловлен наблюдаемой частотой ex post, не является причинно исполнимой live-стратегией и не гарантирует одинаковую продолжительность позиций.

Anchored walk-forward: train2020→test2021; train2020–21→test2022; train2020–22→test2023; train2020–23→test2024. При каждом выборе используются только train-данные, фиксированный standalone subset (NONE, две stop policies), отдельный баланс test. Если статистические критерии не выполнены, численно выбранный пример остаётся описательным. Сравнение не оптимизирует параметры по2025.

Buy-and-hold2000 USDT — отдельный ориентир, без protective SL/эквивалентного риска. На периодах с разрывами полный buy-and-hold PnL не утверждается. Прежние17 стратегий/зеркальные версии остаются в неизменённом AURA_SIX_YEAR_BACKTEST; результаты не переписаны и не объединены в одинаковое ранжирование при различии execution/risk/TF/warmup.

## Запуск и воспроизводимость

```bash
mkdir -p /tmp/aura-pattern-v2
cp docs/AURA_PATTERN_RESEARCH_2_PROTOCOL.json /tmp/aura-pattern-v2/protocol.json
python -B scripts/run_pattern_research.py /path/AURA_BTCUSDT_15m_2020-2025.zip \
  --output /tmp/aura-pattern-v2 --report docs/AURA_PATTERN_RESEARCH_2.json
python -B scripts/pattern_research_controls.py --output /tmp/aura-pattern-v2 \
  --report docs/AURA_PATTERN_RESEARCH_2.json
python -B scripts/audit_pattern_research.py /tmp/aura-pattern-v2
python -B scripts/audit_pattern_controls.py /tmp/aura-pattern-v2
python -B scripts/report_pattern_research.py --output /tmp/aura-pattern-v2 \
  --report docs/AURA_PATTERN_RESEARCH_2.json --markdown docs/AURA_PATTERN_RESEARCH_2.md
python -B -m unittest tests.test_pattern_research -v
```

`--max-jobs` / `--seconds` ограничивают primary runner между jobs; каждый job ограничен конечной историей. Для исходного frozen manifest копируйте committed protocol в новый output, как в команде выше. При старте без него будет новый provenance SHA с теми же параметрами. Повтор той же команды resume, проверка SHA artifacts/архива/кода/протокола; изменённый source/config отклоняется. Не нужно запускать это на Render Free: только offline CPU research. Контролируется RAM: архив≤211000 rows, одна TF cache за раз; полные journals/curves сжатые внеgit, в git только агрегаты. Gzip mtime0, canonical JSON, стабильный seed. Это не HTTP endpoint и не background learner.

## Проверки и review

Результаты вычисления и проверок добавляются ниже после завершения, без подмены synthetic fixtures реальной оценкой доходности.

Resume review: исправлено сравнение JSON list/Python tuple посредством canonical digest. Единственный pre-fix source SHA совместим только при pinned hash десяти неизменённых математических/детекторных модулей и идентичном parameter manifest; исходный frozen manifest не переписывается. Implementation source hash сохранён отдельно. Формулы и результаты исполнения не изменены.

Дополнительные regression fixes runner: квалифицированный кандидат обязательно включается в validation, даже если десять более высоких numerical результатов не проходят gates; отсутствие сделок маркируется INSUFFICIENT_EVIDENCE, а не потерей денег. Ни одна формула исполнения не изменена.

## Фактически завершённый расчёт

Статус: **NO_EDGE_FOUND**. Проверены 30 зарегистрированных детекторов на трёх TF; 810 development-гипотез, baseline+stress. Development-классы: `{'REJECTED': 682, 'INSUFFICIENT_EVIDENCE': 128}`.
Положительный полностью наблюдаемый development net: 97 из810. Validation: 10 описательных прогонов плюс stress; финалисты: 0; trading-прогоны2025: 0.
Всего primary jobs: 1640. Сумма closed trades по810 baseline-гипотезам: 251696. Это сумма разных симуляций с пересечениями, не число независимых рыночных событий.
Protocol SHA256: `82e1379544db80b9f6287b07c494bd90b78a37441362809ae6dc12e724463939`; finalists lock SHA256: `5c58e9de76d02678e8a64d2f20352edc0e7e171b2b720ea258196349b7b53d0e`.

### Top10 development — числовой рейтинг, не список разрешённых стратегий

| ID | Net USDT | Trades | Class | Причины |
|---|---:|---:|---|---|
| 1h:atr_expansion:NONE:ATR_2_4 | 954.34130541 | 199 | REJECTED | CENSORED_GAP |
| 1h:long_legged_doji:VOL_HIGH:PCT_2_4 | 936.12182503 | 61 | INSUFFICIENT_EVIDENCE | TOO_FEW_TRADES, MULTIPLE_COMPARISON_UNCERTAINTY |
| 1h:swing_high:VOL_HIGH:PCT_2_4 | 887.41856495 | 158 | INSUFFICIENT_EVIDENCE | STRESS_NEGATIVE, MULTIPLE_COMPARISON_UNCERTAINTY, BLOCK_CI_NONPOSITIVE |
| 1h:spinning_top:VOL_HIGH:PCT_2_4 | 829.80395164 | 137 | INSUFFICIENT_EVIDENCE | STRESS_NEGATIVE, MULTIPLE_COMPARISON_UNCERTAINTY, BLOCK_CI_NONPOSITIVE |
| 15m:swing_high:VOL_HIGH:PCT_2_4 | 789.40658060 | 446 | REJECTED | CENSORED_GAP |
| 15m:spinning_top:VOL_HIGH:PCT_2_4 | 787.60378881 | 417 | REJECTED | CENSORED_GAP |
| 1h:swing_low:VOL_LOW:PCT_2_4 | 715.82060056 | 57 | INSUFFICIENT_EVIDENCE | TOO_FEW_TRADES, YEAR_UNSTABLE, MULTIPLE_COMPARISON_UNCERTAINTY, BLOCK_CI_NONPOSITIVE |
| 1h:doji:VOL_HIGH:PCT_2_4 | 713.62366461 | 113 | INSUFFICIENT_EVIDENCE | MULTIPLE_COMPARISON_UNCERTAINTY, BLOCK_CI_NONPOSITIVE |
| 15m:swing_low:VOL_HIGH:PCT_2_4 | 674.39996533 | 478 | REJECTED | CENSORED_GAP |
| 1h:spinning_top:TREND_VOLUME:PCT_2_4 | 552.71217734 | 157 | REJECTED | CENSORED_GAP |

### Validation

| ID | Net USDT | Trades | PF | DD% | Class/scope |
|---|---:|---:|---:|---:|---|
| 1h:long_legged_doji:VOL_HIGH:PCT_2_4 | -440.21798642 | 55 | 0.67276282 | 6.10683169 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 1h:swing_high:VOL_HIGH:PCT_2_4 | -611.47703607 | 159 | 0.83594272 | 9.26533712 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 1h:spinning_top:VOL_HIGH:PCT_2_4 | -23.30243794 | 122 | 0.99111358 | 5.07706429 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 1h:swing_low:VOL_LOW:PCT_2_4 | -366.89446810 | 95 | 0.79906169 | 5.83405321 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 1h:doji:VOL_HIGH:PCT_2_4 | -455.95241686 | 115 | 0.82015491 | 7.94736461 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 15m:fvg:VOL_LOW:PCT_2_4 | 35.29798837 | 246 | 1.00688476 | 7.94001920 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 1h:inverted_hammer:SR:PCT_2_4 | 89.45823142 | 14 | 1.39830859 | 1.32300739 | INSUFFICIENT_EVIDENCE / EXPLORATORY_NOT_ELIGIBLE |
| 1h:inside_bar:VOL_HIGH:PCT_2_4 | 267.87796765 | 177 | 1.07547175 | 6.30600286 | INSUFFICIENT_EVIDENCE / EXPLORATORY_NOT_ELIGIBLE |
| 1h:hanging_man:TREND:PCT_2_4 | -89.05237053 | 42 | 0.89106527 | 6.06341430 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |
| 15m:hanging_man:VOLUME:PCT_2_4 | -1013.46630984 | 88 | 0.53974551 | 13.04228005 | REJECTED / EXPLORATORY_NOT_ELIGIBLE |

### Причины отбраковки

`{'BLOCK_CI_NONPOSITIVE': 96, 'CENSORED_GAP': 380, 'MULTIPLE_COMPARISON_UNCERTAINTY': 97, 'NET_NONPOSITIVE': 659, 'NO_TRADES': 31, 'STRESS_NEGATIVE': 47, 'TOO_FEW_TRADES': 91, 'YEAR_UNSTABLE': 88}`. Причины могут пересекаться; суммы не являются числом отдельных гипотез.

**Финалистов нет; 2025 не использован для поиска победителя. ПОДТВЕРЖДЁННОЙ ПРИБЫЛЬНОЙ СТРАТЕГИИ НЕТ.** Положительные числовые development-результаты не выдерживают заданный набор статистических, календарных или стресс-критериев. Не ослаблять пороги для красивого результата.

### Контроли и walk-forward

Контрольных симуляций: 42; walk-forward folds: 12. Полные результаты в JSON.

| TF | Test year | Net USDT | Trades | Выбор только по прошлому |
|---|---:|---:|---:|---|
| 15m | 2021 | -50.96212555 | 41 | 15m:atr_compression:NONE:PCT_2_4 |
| 15m | 2022 | -168.37818650 | 99 | 15m:atr_compression:NONE:PCT_2_4 |
| 15m | 2023 | -588.76824135 | 139 | 15m:atr_compression:NONE:PCT_2_4 |
| 1h | 2021 | -104.75552710 | 13 | 1h:atr_compression:NONE:PCT_2_4 |
| 1h | 2022 | -364.26448650 | 66 | 1h:inverted_hammer:NONE:ATR_2_4 |
| 1h | 2023 | -58.40173586 | 52 | 1h:atr_compression:NONE:PCT_2_4 |
| 1h | 2024 | 16.07221003 | 55 | 1h:atr_compression:NONE:PCT_2_4 |
| 4h | 2021 | 73.65637388 | 24 | 4h:bullish_engulfing:NONE:ATR_2_4 |
| 4h | 2022 | -298.38823055 | 17 | 4h:marubozu:NONE:PCT_2_4 |
| 4h | 2023 | -1.69556258 | 20 | 4h:shooting_star:NONE:ATR_2_4 |
| 4h | 2024 | -403.31230808 | 25 | 4h:shooting_star:NONE:ATR_2_4 |

### Независимая проверка и ограничения

Accounting audit: `{'closed_trades_checked': 508204, 'errors': 0, 'jobs_checked': 1640, 'method': 'Independent exact Fraction adverse fills, Decimal ceil fees, next-open/touch/side/risk/overlap checks and independently reconstructed cash/liquidation equity/drawdown. Conditional gap ledgers checked as conditional, not asserted investable.'}`.
Control audit: `{'closed_trades_checked': 13242, 'errors': 0, 'jobs_checked': 53, 'scope': 'All delivered matched random/simple baseline and executed walk-forward test portfolios; training-selection portfolios use engine internal guards, not included in this independent count. Buy-hold is separately risk-non-equivalent.'}`.
Checks: `{'app_main_import': 'PASS', 'environment': {'fastapi': '0.141.1', 'httpx': '0.28.1', 'numpy': '2.3.5', 'python': '3.12.14', 'requirements_environment_matches': False, 'starlette': '1.6.0'}, 'exchange_boundary': 'No network/private-account client imports or exchange-write calls in new research code; protected production sources unchanged.', 'full_pytest': 'NOT RUN: No module named pytest; total unexecuted cases not enumerated', 'javascript_failures': 0, 'javascript_passed': 106, 'new_research_tests': 23, 'python_failures': 0, 'python_unittest_passed': 125, 'render_android': 'NOT RUN / unchanged', 'review_fixes': ['bootstrap resolution increased before final selection', 'years without trades fail yearly gate', 'canonical list/tuple resume fix with pinned legacy compatibility', 'qualified candidate included in validation even below top10 numerical', 'zero-trade cases classified insufficient'], 'review_limitations': ['bootstrap stationarity/block length assumptions', '2025 already observed', 'conditional gap ledgers cannot qualify', 'single research process per output directory', 'CLI seconds budget checked between finite jobs', 'full pytest missing', 'installed dependency versions differ from requirements'], 'reviews': ['architecture', 'Python', 'security', 'trading mathematics', 'causality', 'gap/restart', 'testing'], 'security': 'Static code review + heuristic private-key/AWS scan; no findings. Not exhaustive secret detection.', 'syntax_javascript_files': 8, 'syntax_python_files': 110}`.
Полные journals и candle-level equity curves находятся внеgit в сжатых hash-addressed artifacts; воспроизводятся командами выше. JSON содержит все810 гипотез, агрегаты, hashes, подробную data-quality карту и occurrences. Grouped economy arrays имеют схему grouped_economy_columns; yearly/monthly PnL — атрибуция закрытых сделок по exit date, не отдельные ежегодно перезапущенные портфели.
Walk-forward контрольный числовой выбор также не превращается в production-кандидата автоматически. Интервалы/пороговые detec­tors и блок14 дней — исследовательские допущения. Нет независимой гарантии edge, нет multiple-testing-adjusted новой2025 проверки.
Следующий безопасный шаг: заранее определить новый отложенный forward-период, собрать данные и проверять небольшое число заранее обоснованных механизмов/микроструктурных гипотез. Ничего не включать в Auto Paper по этой сетке.
Render, Android/live UI в этой задаче не проверялись и не изменялись.

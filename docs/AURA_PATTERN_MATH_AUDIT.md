# Математический аудит Historical Pattern: сентябрь 2026

## Вывод и статус

**COMPLETE**, использован доступный исходный CSV, не синтетическая история.
Подтверждённых ошибок production-математики, искусственно уменьшающих число
аналогов в данном прогоне, **не обнаружено**. Это вывод о проверенных формулах
и инвариантах, не доказательство отсутствия любых дефектов или пригодности
стратегии к торговле. Production-код и настройки не менялись.

Главное измеренное ограничение — **similarity ≥75% до purge**. Среди тысяч
доступных окон на каждой свече через этот порог прошли максимум одно окно.
`minimum_sample=20` (так называется поле в коде, в единственном числе) является
необходимым фильтром, но не единственной причиной WAIT: одновременно не
проходят confidence и Wilson. Простое удаление sample gate не даёт сигнала.

## Данные и воспроизводимость

CSV `BTCUSDT-15m-2026-05_to_09.csv`, 14 688 строк, Binance 12 колонок,
microseconds, весь файл валидирован существующим локальным импортёром.
SHA256: `cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`.
Отдельная проверка подлинности архива через сеть не проводилась.

Тестовые свечи: 2880 с open UTC в `[2026-09-01,2026-10-01)`.
Baseline: ровно 10 000 предыдущих свечей, затем накопление истории в сентябре,
как в предыдущем replay. Previous JSON SHA256:
`c619e6cde836bc3a7a20cfb1bc997c5bebf1ab4a327c54d0d193610179441ca1`.
Все **2880** заново рассчитанных baseline сигналов и confidence совпали с этим
JSON; совпали также счётчики failed gates. Исследование не запускало Paper
execution повторно: оно измеряет окна и production decide, не прибыль сетки.

Диагностика: `scripts/audit_pattern_math.py`; полный JSON с показателями
каждой сентябрьской свечи, гистограммами, парами/комбинациями отказов,
30 конфигурациями и сравнением истории:
`docs/AURA_PATTERN_MATH_AUDIT.json`.
SHA256 этого JSON: `b5e4e1384edf753ad786eee5ed759673dcec2ede19733d2a04f698d28ca7e147`.
SHA256 production-файлов и диагностического скрипта записаны в JSON.
Baseline code revision: `a274a0994aa0b390f17d5ff070fcd74a05ca6f90`.

```bash
python -B scripts/audit_pattern_math.py BTCUSDT-15m-2026-05_to_09.csv \
  --baseline docs/AURA_SEPTEMBER_2026_BACKTEST.json \
  --max-seconds 600 --output /tmp/aura-pattern-math-audit.json
```

Новый output обязателен. Нет network, credentials, live database или UI writes.
600s — ограниченный бюджет standalone исследования, не web/Render worker job.

## Проверенные формулы и индексы

`features.py`: EMA20/50/200 и MACD12/26/9 причинно seeded, RSI/ATR14 Wilder,
логарифмические returns, 21 context feature и 20×5=100 sequence features.
Цены/движения нормированы ATR, часть отношений — close/returns; volume —
отношение к предыдущим 20 наблюдениям. Нормализация `tanh(x/3)` фиксированная,
не fitted на сентябре. Missing volume исключается маской, не подделывается.
Valid feature start — index499 при context500; все необходимые индикаторы
к этому индексу прогреты. Проверены независимые scale/future-инварианты
существующими тестами. Вектор может быть предварительно вычислен для всей
серии, но координаты и facts каждого i зависят только от ≤i.

`matching.py`: для query t кандидаты `[499,t-20-50]`, inclusive.
Первой сентябрьской свече t10000 доступны `10000-70-499+1=9432` окна.
Forward outcome кандидата заканчивается не позже t−20, а query pattern
начинается t−19: будущие исходы не пересекают query pattern.
Сравниваются только query t и уже допустимые кандидаты; future vectors не читаются.
MTF собирает только полностью закрытые buckets на cutoff t close.

На общих finite координатах:

```text
a = mean((candidate_core - query_core)^2)      # 21 координата
b = mean((candidate_sequence - query_sequence)^2) # 100 координат
d = sqrt((a+b)/2)
similarity_percent = 100 * exp(-3*d)
```

Каждая группа имеет половину веса; 100 sequence координат не получают
100/21-кратный вес. Маска исключает только missing координаты, делитель —
число имеющихся координат. Порог75 корректно означает d≤0.0958940,
порог60 — d≤0.1702752. Score не является процентом совпадающих свечей или
вероятностью выигрыша. Строгая геометрическая близость в 121 координате —
объяснимый design constraint, не найденная ошибка percent conversion.

Stable sort — similarity descending, при равенстве раньше исторический индекс.
Greedy purge-distance=lookback20+max horizon50=70 баров. Паттерн+исход
кандидата покрывает `[i−19,i+50]` (70 баров); разница индексов70 допустима,
69 — пересечение. max_matches100 применяется после purge. Граничная индексация
и tie order проверены диагностическими тестами; reference find_matches совпал
для всех six thresholds на четырёх контрольных свечах каждой глубины.

`outcomes.py`: `(future_close/entry_close−1)*100`, UP>0, DOWN<0, FLAT=0.
SHORT учитывает отрицательный знак направления при expected mean/median.
При равенстве направленных частот предпочитается LONG, но evidence gates
всё равно применяются; отсутствие matches не становится LONG.
Стратегический cost5 bps сравнивается с move0.05%, а не5%. Paper fee0.10%
per side не подменяет этот сохранённый production фильтр.

Confidence:

```text
100 * min(1, n/(2*minimum_sample)) * average_similarity/100
    * directional_rate/100 * (0.5+0.5*consistency)
    * min(1, 1/volatility_ratio) * (0.75+0.25*mtf_confirmation)
```

Порог40 проверяется до округления display score до двух знаков. Wilson95%
для 1 успеха из1 равен20.6543% (lower bound), а не100%: rejection корректен.
Независимый RMS-эталон, сравнение selection с production и baseline
per-candle confidence исключили найденную в проверяемых данных ошибку шкалы,
sort/purge/направления или индексов. Production regression fix не потребовался.

## Статистика при production 75% / 20

| Показатель | Min | Median | Mean | Max |
| --- | ---: | ---: | ---: | ---: |
| Доступно исторических окон | 9432 | 10871.5 | 10871.5 | 12311 |
| Проходит similarity≥75 | 0 | 0 | 0.00520833 | 1 |
| После purge, до cap | 0 | 0 | 0.00520833 | 1 |
| Выбрано production после cap100 | 0 | 0 | 0.00520833 | 1 |

Распределение всех трёх стадий отбора одинаково: **0 аналогов — 2865 свечей,
1 аналог — 15**. Всего отобранных аналоговых наблюдений по решениям —15,
а не 15 независимых исторических объектов. Purge и cap100 при75 ничего
не удалили. В 15 nonempty случаях directional_analogues=1; 12 ориентаций LONG,
3 SHORT. Это не подтверждённые сигналы.

Exact intersection patterns:

- 2865: все семь gates fail (нет аналогов).
- 14: одновременно MINIMUM_SAMPLE, WILSON, CONFIDENCE.
- 1: те же три и дополнительно EXPECTED_MOVE_COST.

Попарное пересечение каждой пары из sample/Wilson/confidence — **2880**.
Для direction/median/consistency —2865; cost —2866. Полные 21 попарных
пересечений содержатся в JSON. Ни один gate не оказался единственным
блокером хотя бы на одной production-свече. Удаление только sample gate:
**0** сигналов. Максимальный raw confidence — **1.908472**, при требуемых40.
Даже при minimum_sample5 и similarity75 максимальный score —7.633888.

## 10 лучших свечей по числу аналогов

У всех n1; tie-break — ближайшая similarity descending, затем open UTC.
Дата ниже — **open**, решение принимается через15 минут на close.
Каждый из10 случаев fails MINIMUM_SAMPLE, WILSON, CONFIDENCE.

| Open UTC | Направление аналога | n | Similarity% | Raw confidence |
| --- | --- | ---: | ---: | ---: |
| 09-12 03:45 | LONG | 1 | 77.5504 | 1.4541 |
| 09-12 05:30 | LONG | 1 | 76.9832 | 1.4434 |
| 09-22 22:30 | LONG | 1 | 76.3389 | 1.9085 |
| 09-12 04:45 | LONG | 1 | 76.3001 | 1.4306 |
| 09-02 07:30 | LONG | 1 | 76.1502 | 1.6658 |
| 09-04 03:45 | SHORT | 1 | 76.0291 | 1.0692 |
| 09-22 06:15 | LONG | 1 | 75.9162 | 1.8979 |
| 09-19 00:30 | SHORT | 1 | 75.8163 | 1.4216 |
| 09-22 06:00 | LONG | 1 | 75.5938 | 1.6536 |
| 09-22 22:15 | LONG | 1 | 75.5150 | 1.8879 |

09-22 06:00 дополнительно fails cost: аналоговое движение0.00367647%
меньше0.05%. У остальных top10 directional outcome достаточно положителен
для своей стороны, но единственное наблюдение статистически недостаточно.
Все подробные up/down/flat, available/pre/post counts, median/mean, Wilson,
confidence и rejected gates каждой из2880 свечей сохранены в JSON.

## Research sensitivity: 30 конфигураций, не выбор production параметров

Все параметры кроме двух исследуемых оставлены PatternConfig defaults.
minimum_sample меняется одновременно в explicit sample gate и confidence
sample factor, как требует production decide. Одного изменения n≥threshold
в диагностике было бы недостаточно для корректного сравнения.

Среднее/медиана/max отобранных аналогов по similarity:

| Similarity | Mean before purge | Mean after | Median after | Max before / after |
| --- | ---: | ---: | ---: | ---: |
| 60 | 90.8333 | 18.2910 | 18 | 667 / 57 |
| 65 | 10.6622 | 4.4358 | 2 | 176 / 29 |
| 70 | 0.521181 | 0.388889 | 0 | 23 / 11 |
| 75 | 0.005208 | 0.005208 | 0 | 1 / 1 |
| 80 | 0 | 0 | 0 | 0 / 0 |
| 85 | 0 | 0 | 0 | 0 / 0 |

Сигналы **LONG/SHORT** на2880 тех же закрытых свечах, WAIT=2880−LONG−SHORT:

| Similarity \ minimum_sample | 5 | 10 | 15 | 20 | 25 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 60 | 7/16 | 6/12 | 6/2 | 1/0 | 0/0 |
| 65 | 1/7 | 0/0 | 0/0 | 0/0 | 0/0 |
| 70 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| 75 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| 80 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| 85 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |

Нижние thresholds дают больше соседей; purge становится заметным ограничением
при60/65. Количество сигналов не монотонно по similarity: состав matches,
directional outcomes, Wilson и confidence меняются вместе. Снижение sample
при65 до10 ещё не создаёт сигналов, хотя max confidence47.4878: другие gates
тоже нужны. Не рассчитаны входы, сделки, PnL или прибыльность этих вариантов.
Нет ranking/optimization и рекомендации выбрать самую активную клетку.

## Глубина истории на одинаковом сентябре

Точная семантика: **initial warm-up** 2000/5000/10000, затем накопление
сентябрьских свечей, как в baseline replay. Это **не** фиксированный rolling
window длиной2000/5000/10000 и не его эквивалент. Индикаторы причинно seeded
заново с начала каждой собственной истории. Comparison здесь —defaults75/20;
30-клеточная sensitivity grid рассчитана только для initial10000.

| Warm-up | Available windows first / last | Mean n | 0 / 1 аналог | LONG/SHORT/WAIT |
| --- | ---: | ---: | ---: | --- |
| 2000 | 1432 / 4311 | 0.00208333 | 2874 / 6 | 0/0/2880 |
| 5000 | 4432 / 7311 | 0.00208333 | 2874 / 6 | 0/0/2880 |
| 10000 | 9432 / 12311 | 0.00520833 | 2865 / 15 | 0/0/2880 |

Для всех глубин min/median/max n=0/0/1. Большая initial history в этом наборе
увеличила число nonempty решений с6 до15, но не приблизила sample к20.
Она также меняет seed индикаторов, так что измерение не является чистым
counterfactual добавлением кандидатов с неизменными features.

## Наблюдения, ограничения и дальнейшая проверка

**Наблюдение:** при production75 никакого массового потери кандидатов на purge
нет. Наибольшая similarity за весь baseline77.5504%, большинство query вообще
не имеют соседа≥75. Нет доказательства, что sample20 является ошибочным числом.

**Design/statistical limitations, не исправляемые ошибки:** greedy similarity-first
отбор не максимизирует число непересекающихся окон; выбор самого похожего
центрального окна может исключить два чуть менее похожих. Это documented
приоритет близости, не ошибка sort. Purge70 разносит pattern+outcome окна, но
их 500-bar context может перекрываться, а рынок зависим во времени. Поэтому
Wilson95% — descriptive bound, не доказанная вероятность прибыли/независимость.
Tanh с фиксированными scale/весами и exp(-3d) — heuristic similarity, не
эмпирическая калибровка рынка. Нулевые сигналы не доказывают defect.

**Гипотеза для исследования:** используемая геометрия/порог слишком редко
находят близких соседей именно в этом sample. Это не доказанная ошибка
формулы. Проверять её следует на других периодах/режимах, заранее фиксируя
метрики и условия, а не подбирая прибыльный threshold на сентябре.

Следующий безопасный шаг: независимая проверка данного JSON/кода; затем
на другом заранее выбранном периоде измерить distribution nearest distance,
вклад context/sequence групп и устойчивость соседей. При необходимости отдельно
спроектировать fixed rolling-depth эксперимент. Эти работы здесь не выполнялись
и production-параметры не изменялись.

## Verification

Полный Python suite: **725 passed**, одна существующая Starlette warning.
Targeted diagnostics/pattern/cache tests: **28 passed**. Добавлены только4
проверки нового диагностического кода: RMS/percent oracle, production selection
equivalence, purge boundary/tie order и overlapping-filter accounting.
Нет production regression fix, потому что обоснованный production defect не найден.
Все пять JS suites: **101 passed** (57 Paper,9 reliability,13 Bybit,11 Testnet,11 Lab).
Python AST syntax/imports, JS syntax, heuristic credential scan и exchange-write/
private-client dependency scan: PASS. Exact requirements-pinned env,
live Render/mobile и реальные аккаунты не тестировались. Нет API/секретов,
активации, SL/TP/risk/commission/UI изменений или новых торговых функций.

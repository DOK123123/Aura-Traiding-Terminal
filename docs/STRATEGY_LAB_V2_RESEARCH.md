# Strategy Lab v2 — annual frozen comparison

Исследование, не автоматическая торговля. Ветка основана на Draft PR #4
(который зависит от #3); production main остаётся c50fd0b. Никаких merge/deploy,
Supabase/балансов/позиций/scheduler writes или реальных биржевых ордеров.

## Данные и независимость

**Источник: Binance Spot BTCUSDT**, фиксированный публичный
`https://data-api.binance.vision/api/v3/klines`, 15m. 1h/4h агрегированы только
из полных непрерывных UTC-блоков этих же свечей. Bybit Futures не используется.
SHORT — условная виртуальная направленная экспозиция, а не фактический Spot
borrow, маржинальный продукт или воспроизведение фьючерсного счёта.

Период: **2025-10-16 00:00 — 2026-10-16 00:00 UTC exclusive**, 365 дней,
35 040 evaluation candles и 4 160 warm-up candles: **39 200 реальных свечей**.
CSV SHA256 `da31330b7d5df5bf9560171372e6f4157d3215ef236ef528a529089f6a823810`.
Данные и acquisition provenance с REST page hashes сохранены в `docs/data/`.
Все 21 728 строк пересечения с предыдущим 6-month CSV совпадают побайтно.
OHLCV/order/gaps/close times/future bounds проверены существующим strict importer
через bounded chunk loader; synthetic bars в историческом расчёте отсутствуют.
REST provenance не является независимой checksum-аттестацией архивного ZIP.

Разделение `floor(35040×7/10) = 24528` свечей на разработку и 10512 на проверку:
**2026-06-28 12:00 UTC** — граница; 255.5 / 109.5 дня, ровно 70/30.
Каждый strategy/TF/split — новый RAM account 10 000 USDT без переноса позиции
или pending через границу. Warm-up использует только прошлую историю.
На границе нет искусственного force close, остаток оценивается liquidation equity.
Development profit не использует последующее закрытие оставшейся позиции.
Full-year результаты описательные, не дополнительный независимый тест.

**Проверочные 30% хронологически отделены и не используются для подбора новых
параметров, но пересекаются с ранее исследованной историей. Это не untouched
blind holdout и не доказательство независимого будущего edge.**
Предыдущие попытки и 9 новых strategy/TF вариантов создают multiple comparisons.
Протокол зафиксирован до расчёта новых финансовых результатов; grid search,
выбора лучших параметров по validation и ретроспективного исключения плохих
сделок/периодов не выполнялось. Новые гипотезы после отчёта потребуют нового
заранее определённого теста, а не переписывания этих результатов.

## Фиксированные семейства

Полный протокол: `STRATEGY_LAB_V2_PROTOCOL.json`.

- **Donchian Breakout:** prior20 high/low, current close за диапазоном на .1 ATR,
  prior close не был за этим уровнем, направленное тело; EMA20/50 соответствует
  направлению, ADX14≥20, relative volume≥1.25. SL2 ATR / TP4 ATR.
- **Trend Following + ATR:** EMA50/200 и slope EMA50 задают направление;
  directed close пересекает EMA20 после previous close с другой стороны;
  ADX14≥20, RSI LONG50–75 / SHORT25–50, volume≥.8. Initial SL3 ATR / TP6 ATR.
  После завершения каждой strategy-TF свечи — chandelier stop по highest/lowest
  наблюдаемому TF extreme с момента входа ±3 текущих ATR. Clamp к closed price,
  только tightening, включая фиксацию прибыли за entry. Новый stop действует
  с **следующего 15m open**, не на вычислившей его свече; TP фиксирован.
- **EMA + RSI + ADX:** EMA20/50 и close за EMA20, RSI crosses55 LONG /45 SHORT,
  ADX14≥20, DI+/DI− соответствует направлению, volume≥.8. SL2 ATR / TP4 ATR.

Каждое семейство применяет одинаковые параметры на **15m, 1h, 4h**: 9 заранее
заданных вариантов. Все поддерживают LONG/SHORT. Current range>3 ATR исключён;
ожидаемый close-time net RR после model fees/slippage должен быть≥1.2.
ATR14/RSI14/ADX14 — Wilder; EMA — SMA seed, затем alpha=2/(n+1).
Новые индикаторы используют причинную историю от начала CSV с прогревом;
ни rolling range, ни volume mean не включают будущие свечи.

Baselines **Aura 4.2 native** и **Aura 4.3 original** сохраняют свои прежние
правила и production rolling start `floor(T/4h)*4h -4160*15m`, native 15m
entries и 1h/4h context. Они не переименовываются в 1h/4h стратегии.
Legacy Lab `AURA_EXISTING / INCOMPATIBLE` — более старая отдельная модель,
её прежние результаты не подменяют это сравнение Auto Paper 4.2.

Native cached states — чистое причинное ускорение только в offline worker.
Для уже проверенного пересечения разрешено переиспользовать **решения**, если
совпали все OHLCV и хэши соответствующего кода/протокола. Финансовые результаты
за год всегда пересчитываются с нового счёта, не склеиваются из старых PnL.
Включён annual native checkpoint, привязанный к data/code/start/end fingerprint;
без него CLI воспроизводит все native windows, без обязательного local seed.

## Исполнение и риск

Для всех 11 вариантов: 10 000 USDT, planned fee-inclusive risk≤0.5%,
notional≤2000, одна позиция, daily loss halt2%, max DD halt10%; fees10bps
и adverse slippage5bps **на каждую сторону**, source Binance Spot.
Нет авто-возобновления PAUSED после risk halt; это прежняя latched политика
4.2. Консервативные gap fills и SL-first при SL/TP в одном OHLC.
Сигнал по closed TF, entry на следующем доступном 15m bar open в идеализированной
next-open модели. Технический execution loop 15m у всех, даже сигналов 1h/4h.
Дубль watermark не создаёт повторный OPEN, missing bars не восстанавливаются
синтетическими данными. На validation дополнительно одинаково задерживается
исполнение **на один 15m бар** для всех вариантов, без изменения параметров.
В сделке отдельно сохранены original TF close, dispatch и entry timestamps.

`app/automated/engine.py` **не изменён**. Новый `app/lab/v2_execution.py` —
изолированный research adapter: переиспользует исходные pure sizing, fees,
marking, risk, open/close/protective functions. Без trailing его transitions
эквивалентны native с учётом дополнительных research timestamp метаданных.
В нём явно расширен только допустимый trailing stop за entry: все прежние
accounting checks применяются к копии с initial stop; реальный ratchet отдельно
проверяется на monotonicity, target bounds и известное время применения.
Production фиксированный stop контракт не менялся; никакого live controller,
storage, private client или activation route новый код не использует.

Исполнение является **OHLC моделью**, не гарантией исторического open после
реальной задержки Render/network. `T+30s` — существующий freshness/processing
контракт; внутрисвечный quote через 30 секунд неизвестен. Delayed validation
оценивает один сценарий задержки, а не доказывает достижимость real fills.
Funding/borrow/spread/market impact/ликвидность/outages не моделируются.
Gap loss может превысить planned0.5%; halt не гарантирует цену исполнения.
DD рассчитывается по каждому open/close liquidation-equity mark, не по
неизвестному tick-level intrabar пути. Ограничения одинаковы для всех.

## Отбор и метрики

Development-only selection среди всех 11 вариантов: ≥30 закрытых сделок,
net>0, PF≥1.1, DD<10%, положительна хотя бы половина полных development месяцев.
Среди допустимых — максимальная expectancy, tie по заранее заданному порядку.
Selection timestamp/hash записывается **до вычисления validation metrics**.
Не допускается заменить выбранный вариант победителем validation.

Предзаданный validation gate: ≥20 закрытых сделок, net>0, PF≥1.1, DD<10%,
положительна хотя бы половина полных validation месяцев; delayed validation
net>0/PF≥1.1. Даже прохождение gate — описательный критерий кандидата,
не statistical significance, независимое подтверждение edge или разрешение PAPER.

Net Profit/Return включают terminal liquidation equity незакрытой позиции.
WR/PF/Expectancy/средняя win/loss — закрытые сделки. Fees — реально начисленные
model fees, включая entry открытого остатка; equity резервирует будущий exit fee.
Sharpe: full UTC daily equity returns, sample stdev, sqrt365, zero RF;
undefined при <20 закрытиях/<30 daily returns/нулевой дисперсии.
Сделок/месяц = closed trades×30/days, не обещание будущей частоты.

LONG/SHORT — realised attribution внутри **общего** single-position portfolio:
count/net/WR/PF/expectancy/fees отдельно. Это не два независимых backtest и не
возможность сложить самостоятельные направления: позиции конкурируют за входы.
Для направлений не выдумываются отдельные DD/Sharpe или unrealized результаты.
Все open/pending позиции и stop history показываются отдельно в деталях.

## Интерфейс и воспроизведение

В Strategy Lab новый блок **Strategy Lab v2**: все 11 строк,
development/validation/full-year/delayed validation, overlay equity с native4.2,
история **всех** сделок, LONG/SHORT attribution/filter, все evaluated-TF decisions
с пагинацией и агрегированные причины execution rejections; failed gates и причины входа/отказа,
original/dispatch/entry timestamps и causal ATR stop history.
Пустые технические 15m ticks без новой 1h/4h свечи не названы strategy decisions.
Полные журналы хранятся отдельными checksum-bound JSONL.gz, не дневной выборкой.

Owner-only GET `/api/lab/v2` и `/api/lab/v2/detail`: fixed artifact paths,
code/checksum/selection/log hashes, bounded gzip/line/row/page limits,
no-store, thread offload; никаких POST/activation/account mutations.
Browser textContent/fixed URLs/abort; нет HTML interpolation или account calls.
Сохранённый отчёт читается без тяжёлого replay на Render.

```bash
gzip -dc docs/data/LAB_V2_BTCUSDT_15m.csv.gz > /tmp/labv2.csv
# Включённый воспроизводимый native checkpoint:
python -m scripts.research_lab_v2 --csv /tmp/labv2.csv \
  --native docs/data/LAB_V2_NATIVE_DECISIONS.gz --output-dir /tmp/labv2
# Чтобы перепроверить native с нуля, вместо bundled checkpoint:
python -m scripts.lab_v2_baselines --csv /tmp/labv2.csv \
  --output /tmp/native.gz --max-seconds 1800
# Если BUDGET_REACHED — повторить точную команду с теми же data/code.
python -m scripts.audit_lab_v2_accounting --report /tmp/labv2/report.json.gz \
  --csv /tmp/labv2.csv --output /tmp/accounting.json
python -m scripts.audit_lab_v2_evidence --directory /tmp/labv2 \
  --csv /tmp/labv2.csv --native docs/data/LAB_V2_NATIVE_DECISIONS.gz \
  --output /tmp/evidence.json
python -m pytest -q
for file in tests/*.cjs; do node "$file"; done
```

Protocol/rules/research execution закреплены коммитом `8049002` до расчёта
новых financial metrics. Это внутренний воспроизводимый frozen protocol,
не сторонняя preregistration. Публикация UI после отдельного разрешения на
merge/deploy — обычным Render процессом, без новых env/SQL/scheduler настроек.
В текущей задаче никаких merge/deploy, реальных или production Paper ордеров.

## Фактические результаты

**NO_ROBUST_ADVANTAGE**. Зафиксированный development winner: **None**.

Selection UTC: `2026-10-16T18:07:58.545149+00:00`; hash `5cefbb3b7fba7538fac755126ea57d99b5a18f1938159bbd705ba12b1308ea32`.

### Development 70%

| Вариант | Сделки | Сделок/30d | Net USDT | Return % | WR % | PF | Expectancy | Max DD % | Sharpe | Fees | Slippage | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 17 | 1.9961 | -204.9760 | -2.0498 | 29.4118 | 0.4896 | -12.0574 | 3.0205 | N/A | 65.2951 | 32.6475 | ON |
| AURA43 | 53 | 6.2231 | -43.0526 | -0.4305 | 37.7358 | 0.9527 | -0.8123 | 3.0434 | -0.1655 | 211.3937 | 105.6969 | ON |
| DONCHIAN_15m | 124 | 14.5597 | -967.4049 | -9.6740 | 30.6452 | 0.6000 | -7.8017 | 10.0160 | -3.4802 | 492.8982 | 246.4491 | PAUSED |
| DONCHIAN_1h | 96 | 11.2720 | -158.8463 | -1.5885 | 37.5000 | 0.9265 | -1.6546 | 5.7718 | -0.3735 | 377.5008 | 188.7505 | ON |
| DONCHIAN_4h | 32 | 3.7573 | -278.8408 | -2.7884 | 31.2500 | 0.7387 | -8.7138 | 4.2183 | -1.0781 | 99.3992 | 49.6996 | ON |
| TREND_ATR_15m | 161 | 18.9041 | -766.5540 | -7.6655 | 28.5714 | 0.6162 | -4.7612 | 9.9225 | -2.8108 | 641.1255 | 320.5628 | ON |
| TREND_ATR_1h | 61 | 7.1624 | -589.8988 | -5.8990 | 24.5902 | 0.4802 | -9.6705 | 7.5169 | -2.7260 | 223.8016 | 111.9007 | ON |
| TREND_ATR_4h | 18 | 2.1135 | 71.7402 | 0.7174 | 38.8889 | 1.2148 | 3.9856 | 1.5976 | N/A | 41.3528 | 20.6764 | ON |
| EMA_RSI_ADX_15m | 68 | 7.9843 | -231.4351 | -2.3144 | 36.7647 | 0.8023 | -3.4035 | 4.8869 | -1.0041 | 271.3809 | 135.6905 | ON |
| EMA_RSI_ADX_1h | 55 | 6.4579 | -445.4006 | -4.4540 | 30.9091 | 0.6700 | -8.0982 | 5.4573 | -1.6275 | 217.2447 | 108.6223 | ON |
| EMA_RSI_ADX_4h | 15 | 1.7613 | -88.3826 | -0.8838 | 33.3333 | 0.8196 | -5.8922 | 2.3584 | N/A | 47.6299 | 23.8149 | ON |

### Validation 30%

| Вариант | Сделки | Сделок/30d | Net USDT | Return % | WR % | PF | Expectancy | Max DD % | Sharpe | Fees | Slippage | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 5 | 1.3699 | -39.2762 | -0.3928 | 20.0000 | 0.4728 | -7.8552 | 0.8560 | N/A | 19.9807 | 9.9903 | ON |
| AURA43 | 4 | 1.0959 | 7.5900 | 0.0759 | 50.0000 | 1.1108 | 1.8975 | 0.6865 | N/A | 15.9602 | 7.9801 | ON |
| DONCHIAN_15m | 18 | 4.9315 | -54.8357 | -0.5484 | 38.8889 | 0.7992 | -3.0464 | 1.4773 | N/A | 72.0745 | 36.0373 | ON |
| DONCHIAN_1h | 31 | 8.4932 | -307.7369 | -3.0774 | 25.8065 | 0.5592 | -9.9270 | 4.4368 | -2.2701 | 124.4113 | 62.2056 | ON |
| DONCHIAN_4h | 13 | 3.5616 | -310.2906 | -3.1029 | 23.0769 | 0.4411 | -21.0595 | 3.3738 | N/A | 49.3424 | 24.6716 | ON |
| TREND_ATR_15m | 28 | 7.6712 | -257.4523 | -2.5745 | 21.4286 | 0.2801 | -9.1947 | 2.7369 | -4.6037 | 111.8305 | 55.9152 | ON |
| TREND_ATR_1h | 23 | 6.3014 | -228.9414 | -2.2894 | 21.7391 | 0.3360 | -9.9540 | 2.6651 | -3.3387 | 92.0546 | 46.0273 | ON |
| TREND_ATR_4h | 7 | 1.9178 | -51.2633 | -0.5126 | 14.2857 | 0.6297 | -7.3233 | 0.9851 | N/A | 19.9260 | 9.9630 | ON |
| EMA_RSI_ADX_15m | 5 | 1.3699 | 34.7081 | 0.3471 | 60.0000 | 1.5624 | 6.9416 | 0.6495 | N/A | 19.9137 | 9.9569 | ON |
| EMA_RSI_ADX_1h | 21 | 5.7534 | -416.2909 | -4.1629 | 14.2857 | 0.2133 | -19.8234 | 4.2401 | -4.4117 | 84.1997 | 42.0998 | ON |
| EMA_RSI_ADX_4h | 6 | 1.6438 | -266.6813 | -2.6668 | 0.0000 | 0.0000 | -46.0176 | 3.5771 | N/A | 25.0738 | 12.5373 | ON |

### Полные 12 месяцев — описательно

| Вариант | Сделки | Сделок/30d | Net USDT | Return % | WR % | PF | Expectancy | Max DD % | Sharpe | Fees | Slippage | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 22 | 1.8082 | -244.2522 | -2.4425 | 27.2727 | 0.4870 | -11.1024 | 3.3957 | -1.5559 | 85.2758 | 42.6379 | ON |
| AURA43 | 57 | 4.6849 | -35.4626 | -0.3546 | 38.5965 | 0.9637 | -0.6222 | 3.4058 | -0.1054 | 227.3539 | 113.6770 | ON |
| DONCHIAN_15m | 124 | 10.1918 | -967.4049 | -9.6740 | 30.6452 | 0.6000 | -7.8017 | 10.0160 | -2.8961 | 492.8982 | 246.4491 | PAUSED |
| DONCHIAN_1h | 127 | 10.4384 | -466.5832 | -4.6658 | 34.6457 | 0.8368 | -3.6739 | 8.1725 | -0.8762 | 501.9121 | 250.9561 | ON |
| DONCHIAN_4h | 45 | 3.6986 | -582.4834 | -5.8248 | 28.8889 | 0.6464 | -12.1554 | 6.3660 | -1.5503 | 147.7550 | 73.8779 | ON |
| TREND_ATR_15m | 164 | 13.4795 | -781.4697 | -7.8147 | 28.0488 | 0.6116 | -4.7651 | 10.0495 | -2.3879 | 653.1126 | 326.5563 | PAUSED |
| TREND_ATR_1h | 84 | 6.9041 | -815.3941 | -8.1539 | 23.8095 | 0.4476 | -9.7071 | 9.5083 | -2.8513 | 315.4072 | 157.7035 | ON |
| TREND_ATR_4h | 25 | 2.0548 | 20.1092 | 0.2011 | 32.0000 | 1.0425 | 0.8044 | 1.5976 | 0.1061 | 61.4217 | 30.7109 | ON |
| EMA_RSI_ADX_15m | 73 | 6.0000 | -196.7270 | -1.9673 | 38.3562 | 0.8404 | -2.6949 | 4.8869 | -0.6778 | 291.2946 | 145.6474 | ON |
| EMA_RSI_ADX_1h | 76 | 6.2466 | -861.6915 | -8.6169 | 26.3158 | 0.5413 | -11.3380 | 9.0954 | -2.3601 | 301.4444 | 150.7221 | ON |
| EMA_RSI_ADX_4h | 21 | 1.7260 | -354.1822 | -3.5418 | 23.8095 | 0.5249 | -17.3146 | 4.1105 | -1.2832 | 72.6404 | 36.3207 | ON |

### Validation +15m задержка исполнения

| Вариант | Сделки | Сделок/30d | Net USDT | Return % | WR % | PF | Expectancy | Max DD % | Sharpe | Fees | Slippage | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 5 | 1.3699 | -32.7756 | -0.3278 | 20.0000 | 0.5377 | -6.5551 | 0.7916 | N/A | 19.9872 | 9.9936 | ON |
| AURA43 | 4 | 1.0959 | -21.9197 | -0.2192 | 50.0000 | 0.7028 | -5.4799 | 0.7355 | N/A | 15.9698 | 7.9849 | ON |
| DONCHIAN_15m | 19 | 5.2055 | -126.1981 | -1.2620 | 36.8421 | 0.5800 | -6.6420 | 1.9551 | N/A | 74.8987 | 37.4493 | ON |
| DONCHIAN_1h | 31 | 8.4932 | -293.1057 | -2.9311 | 25.8065 | 0.5787 | -9.4550 | 4.2985 | -2.1939 | 124.4597 | 62.2298 | ON |
| DONCHIAN_4h | 13 | 3.5616 | -305.2414 | -3.0524 | 23.0769 | 0.4403 | -20.6687 | 3.3952 | N/A | 49.4873 | 24.7441 | ON |
| TREND_ATR_15m | 27 | 7.3973 | -273.2090 | -2.7321 | 18.5185 | 0.2454 | -10.1189 | 2.7518 | -5.3144 | 108.0383 | 54.0191 | ON |
| TREND_ATR_1h | 23 | 6.3014 | -217.1590 | -2.1716 | 26.0870 | 0.3539 | -9.4417 | 2.5653 | -3.1783 | 91.8756 | 45.9378 | ON |
| TREND_ATR_4h | 7 | 1.9178 | -37.2691 | -0.3727 | 28.5714 | 0.7246 | -5.3242 | 0.9978 | N/A | 20.8334 | 10.4167 | ON |
| EMA_RSI_ADX_15m | 5 | 1.3699 | 13.9621 | 0.1396 | 60.0000 | 1.2634 | 2.7924 | 0.6518 | N/A | 19.9453 | 9.9727 | ON |
| EMA_RSI_ADX_1h | 21 | 5.7534 | -451.9099 | -4.5191 | 14.2857 | 0.2053 | -21.5195 | 4.5191 | -4.4515 | 83.7003 | 41.8501 | ON |
| EMA_RSI_ADX_4h | 6 | 1.6438 | -245.6139 | -2.4561 | 0.0000 | 0.0000 | -42.7063 | 3.6963 | N/A | 25.7320 | 12.8665 | ON |

### LONG / SHORT за полный год и validation

Это realised attribution общего single-position portfolio, без выдуманных directional DD/Sharpe.

| Выборка | Вариант | Side | Closed | Net USDT | WR % | PF | Expectancy | Fees |
|---|---|---|---:|---:|---:|---:|---:|---:|
| validation | AURA42 | LONG | 5 | -39.2762 | 20.0000 | 0.4728 | -7.8552 | 19.9807 |
| validation | AURA42 | SHORT | 0 | 0.0000 | N/A | N/A | N/A | 0.0000 |
| full_12m | AURA42 | LONG | 11 | -152.6435 | 18.1818 | 0.2829 | -13.8767 | 43.8912 |
| full_12m | AURA42 | SHORT | 11 | -91.6088 | 36.3636 | 0.6520 | -8.3281 | 41.3846 |
| validation | AURA43 | LONG | 3 | -20.1097 | 33.3333 | 0.7065 | -6.7032 | 11.9919 |
| validation | AURA43 | SHORT | 1 | 27.6996 | 100.0000 | N/A | 27.6996 | 3.9683 |
| full_12m | AURA43 | LONG | 19 | -141.5075 | 31.5789 | 0.6262 | -7.4478 | 75.9344 |
| full_12m | AURA43 | SHORT | 38 | 106.0449 | 42.1053 | 1.1769 | 2.7907 | 151.4195 |
| validation | DONCHIAN_15m | LONG | 14 | -10.1522 | 42.8571 | 0.9494 | -0.7252 | 56.0459 |
| validation | DONCHIAN_15m | SHORT | 4 | -44.6836 | 25.0000 | 0.3825 | -11.1709 | 16.0287 |
| full_12m | DONCHIAN_15m | LONG | 52 | -478.8314 | 28.8462 | 0.5235 | -9.2083 | 207.7289 |
| full_12m | DONCHIAN_15m | SHORT | 72 | -488.5735 | 31.9444 | 0.6543 | -6.7857 | 285.1693 |
| validation | DONCHIAN_1h | LONG | 14 | 57.8970 | 42.8571 | 1.2185 | 4.1355 | 56.1140 |
| validation | DONCHIAN_1h | SHORT | 17 | -365.6339 | 11.7647 | 0.1561 | -21.5079 | 68.2973 |
| full_12m | DONCHIAN_1h | LONG | 50 | -312.4817 | 32.0000 | 0.7277 | -6.2496 | 199.5032 |
| full_12m | DONCHIAN_1h | SHORT | 77 | -154.1015 | 36.3636 | 0.9099 | -2.0013 | 302.4089 |
| validation | DONCHIAN_4h | LONG | 10 | -128.8007 | 30.0000 | 0.6266 | -12.8801 | 36.1546 |
| validation | DONCHIAN_4h | SHORT | 3 | -144.9728 | 0.0000 | 0.0000 | -48.3243 | 11.2976 |
| full_12m | DONCHIAN_4h | LONG | 19 | -315.2578 | 26.3158 | 0.5301 | -16.5925 | 68.5868 |
| full_12m | DONCHIAN_4h | SHORT | 26 | -231.7343 | 30.7692 | 0.7354 | -8.9129 | 77.3311 |
| validation | TREND_ATR_15m | LONG | 16 | -109.3539 | 25.0000 | 0.4357 | -6.8346 | 63.7305 |
| validation | TREND_ATR_15m | SHORT | 12 | -148.0985 | 16.6667 | 0.0960 | -12.3415 | 48.1000 |
| full_12m | TREND_ATR_15m | LONG | 77 | -685.5690 | 20.7792 | 0.2664 | -8.9035 | 307.6221 |
| full_12m | TREND_ATR_15m | SHORT | 87 | -95.9007 | 34.4828 | 0.9110 | -1.1023 | 345.4905 |
| validation | TREND_ATR_1h | LONG | 13 | -73.6889 | 23.0769 | 0.5584 | -5.6684 | 51.9783 |
| validation | TREND_ATR_1h | SHORT | 10 | -155.2525 | 20.0000 | 0.1276 | -15.5252 | 40.0763 |
| full_12m | TREND_ATR_1h | LONG | 32 | -302.2926 | 18.7500 | 0.4341 | -9.4466 | 124.7297 |
| full_12m | TREND_ATR_1h | SHORT | 52 | -513.1015 | 26.9231 | 0.4553 | -9.8673 | 190.6774 |
| validation | TREND_ATR_4h | LONG | 6 | -36.6469 | 16.6667 | 0.7041 | -6.1078 | 17.8073 |
| validation | TREND_ATR_4h | SHORT | 1 | -14.6163 | 0.0000 | 0.0000 | -14.6163 | 2.1187 |
| full_12m | TREND_ATR_4h | LONG | 11 | -40.0462 | 27.2727 | 0.8321 | -3.6406 | 32.0838 |
| full_12m | TREND_ATR_4h | SHORT | 14 | 60.1554 | 35.7143 | 1.2561 | 4.2968 | 29.3379 |
| validation | EMA_RSI_ADX_15m | LONG | 3 | -27.8324 | 33.3333 | 0.5490 | -9.2775 | 11.9842 |
| validation | EMA_RSI_ADX_15m | SHORT | 2 | 62.5404 | 100.0000 | N/A | 31.2702 | 7.9295 |
| full_12m | EMA_RSI_ADX_15m | LONG | 39 | -461.1062 | 25.6410 | 0.4074 | -11.8232 | 155.6946 |
| full_12m | EMA_RSI_ADX_15m | SHORT | 34 | 264.3792 | 52.9412 | 1.5819 | 7.7759 | 135.6000 |
| validation | EMA_RSI_ADX_1h | LONG | 8 | -98.1276 | 25.0000 | 0.4126 | -12.2659 | 31.9338 |
| validation | EMA_RSI_ADX_1h | SHORT | 13 | -318.1633 | 7.6923 | 0.1214 | -24.4741 | 52.2659 |
| full_12m | EMA_RSI_ADX_1h | LONG | 28 | -400.7506 | 21.4286 | 0.4478 | -14.3125 | 111.7110 |
| full_12m | EMA_RSI_ADX_1h | SHORT | 48 | -460.9409 | 29.1667 | 0.6002 | -9.6029 | 189.7335 |
| validation | EMA_RSI_ADX_4h | LONG | 3 | -141.7125 | 0.0000 | 0.0000 | -47.2375 | 11.7992 |
| validation | EMA_RSI_ADX_4h | SHORT | 3 | -134.3933 | 0.0000 | 0.0000 | -44.7978 | 11.2746 |
| full_12m | EMA_RSI_ADX_4h | LONG | 8 | -119.6686 | 25.0000 | 0.5787 | -14.9586 | 29.9413 |
| full_12m | EMA_RSI_ADX_4h | SHORT | 13 | -243.9381 | 23.0769 | 0.4931 | -18.7645 | 40.6991 |

### Помесячная проверка Trend ATR 4h

| Выборка | Месяц | Closed | Изменение equity USDT | Полный месяц |
|---|---|---:|---:|---|
| development | 2025-10 | 2 | -59.26427204 | False |
| development | 2025-11 | 2 | 49.50107392 | True |
| development | 2025-12 | 2 | -57.50712511 | True |
| development | 2026-01 | 2 | 38.56629003 | True |
| development | 2026-02 | 2 | -19.19735651 | True |
| development | 2026-03 | 1 | -4.41153787 | True |
| development | 2026-04 | 3 | 98.42773452 | True |
| development | 2026-05 | 2 | -17.26066901 | True |
| development | 2026-06 | 2 | 42.88611069 | False |
| validation | 2026-06 | 0 | 14.58438437 | False |
| validation | 2026-07 | 3 | -60.59544789 | True |
| validation | 2026-08 | 0 | 0.00000000 | True |
| validation | 2026-09 | 2 | 64.14202125 | True |
| validation | 2026-10 | 2 | -69.39423588 | False |
| validation_delayed | 2026-06 | 0 | 13.15783653 | False |
| validation_delayed | 2026-07 | 3 | -51.57398009 | True |
| validation_delayed | 2026-08 | 0 | 0.00000000 | True |
| validation_delayed | 2026-09 | 2 | 70.32291066 | True |
| validation_delayed | 2026-10 | 2 | -69.17583698 | False |

N/A — неопределённая метрика/недостаточная выборка, не нулевая прибыль.
Сумма dev+validation может отличаться от full из-за самостоятельного старта
каждого split, открытых позиций на границе и latched risk halts.
Все open/pending состояния, 44 полноразмерных decision logs и 44 equity curves
включены в `docs/LAB_V2/`; отображаемая кривая ≤302 точек, DD — по всем marks.

## Ответы и рекомендация

**Ни одна стратегия не показала устойчивого преимущества.** Ни один из 11
вариантов не прошёл заранее определённый development gate; winner=None был
записан до расчёта validation. Параметры после результатов не оптимизировались.

1. **Лучшая стратегия?** Подтверждённой лучшей нет. Единственный положительный
   годовой вариант — Trend Following + ATR 4h — имеет +20.11 USDT за 25 сделок,
   PF1.0425 и expectancy +0.8044 USDT. На development всего 18 сделок, на
   validation 7 сделок и −51.26 USDT (−0.5126%, PF0.6297). Положительный год
   не является устойчивым преимуществом на независимой выборке.
2. **Частота этого описательного кандидата:** 2.05 сделки на 30 дней за полный
   год; 1.92 на validation. Это не обещанная будущая частота и не выбранный winner.
3. **Чистая доходность:** +0.2011% за год после fees/slippage; validation
   −0.5126%, delayed validation −0.3727%. Ни один общий положительный годовой
   результат не выдержал требуемую проверку.
4. **Max DD:** Trend ATR4h =1.5976% за год, validation0.9851%; это open/close
   liquidation-equity метрика, не доказанный tick-level tail risk.
5. **Подтверждённый edge?** Нет. EMA/RSI/ADX15m имеет +34.71 USDT на validation
   (PF1.5624), но только **5 сделок**, отрицательные dev/full-year, а с задержкой
   прибыль снижается до +13.96. Aura4.3 validation +7.59 по 4 сделкам становится
   −21.92 при задержке. Ни одну из этих строк нельзя выбрать задним числом.
6. **Что дальше проверять в PAPER?** Ни одну как подтверждённо улучшенную
   стратегию. Оставить все варианты в Lab. Если отдельно продолжать исследования,
   Trend ATR4h — лишь гипотеза для нового заранее заданного forward-наблюдения;
   текущие результаты не обосновывают её включение в действующий Auto Paper.
   Не включать автоматически, не переключать production и не менять риск.

Donchian15m и TrendATR15m в полном годовом account перешли в PAUSED по max-DD,
с наблюдаемым DD10.016%/10.049%. Защита сработала, не отключалась и не сбрасывалась.
Порог10% — триггер остановки новых входов, не гарантия отсутствия небольшого
overshoot при gap/дискретном mark. Поэтому полная частота включает оставшийся
paused период; отдельная validation начинается с нового account по протоколу.
Почти все остальные варианты убыточны и за год, и на проверке; это явно
отрицательный результат исследования, а не обещание найти прибыльную стратегию.

## Проверки и review

- **1230 Python tests passed**, 1 upstream Starlette/AnyIO deprecation warning,
  158.98 s. Только временный test runner использовал sandbox poll accommodation;
  production event loop не менялся. **19 JavaScript suites passed**.
- Независимый Decimal-64 accounting oracle: **PASS**, 44 прогона,
  **1840 trade records** с повторениями full/split/delay (не столько уникальных
  сделок). OHLC first-touch/gaps/SL-first, initial fee-inclusive risk/quantity,
  next-open/raw prices, комиссии/slippage, PnL/balance, LONG/SHORT attribution,
  все daily equity и bar open/close marks/Max DD проверены.
- Indicator/causality/native audit: **PASS**, 411600 сравнений элементов
  indicator arrays (включая warm-up None) с независимым Decimal oracle;
  **6750 causal trailing updates** проверены по исходным экстремумам/ATR/close
  и времени применения. Изменение будущих OHLC не меняет прошлые решения.
- **35 040 native decisions**, 32 реальных snapshot cutoffs всех 15m UTC-фаз
  в dev/val, **все 8 baseline strategy/split execution portfolios** совпали с
  неизменённым production pure engine по сделкам/балансу/equity/fees/DD.
- Все hashes полных decision artifacts, selection из development, actual
  manifest reader, owner/no-store/GET-only, side filter и pagination проверены.
- AST всех Python, app.main import, changed JS syntax, whitespace и credential
  pattern checks прошли. Старые 90-day и 6-month reports валидны.

**Отдельный code review** по `docs/ecc/TRADING_REVIEW.md`: causal TF boundaries,
ATR effective timestamp, profit-locking ratchet без ослабления initial risk,
validation reset/no future outcome, halt behaviour, exact accounting, undefined
metrics, native fixed-stop equivalence и bounded artifacts проверены. Нет
подтверждённых unresolved critical/high findings в новом research пути.

**Отдельный security review:** pure research не импортирует live controller,
account storage или private clients; GET path/variant/split/side whitelists,
owner/no-store, gzip/hash/size limits, безопасный textContent и bounded fetch/abort.
Публичный downloader фиксирован на Binance GET, TLS/redirect restrictions
сохранены. Credential pattern scan не нашёл совпадений; реальные секреты
не читались и не использовались. Это самостоятельные review passes, не
заявление о независимом внешнем reviewer или полном security scanner.

Остаточные риски: историческая неоднократно изученная выборка, multiple
comparisons, один рыночный год, OHLC/fees/slippage assumptions, неизвестный
intrabar/latency/impact/borrow/funding. Успешные проверки не доказывают edge,
production live autonomous OPEN → CLOSE или реальные fill цены.

Production Aura4.2 strategy/engine/service/storage, Supabase, баланс/позиции,
scheduler, exchange source и historical analog packs не изменены. Ни одного
реального либо production Paper ордера, merge или Render deploy.

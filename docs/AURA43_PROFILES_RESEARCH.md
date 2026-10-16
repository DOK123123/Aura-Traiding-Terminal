# Aura 4.3: Conservative / Balanced / Active — исследование частоты

Это продолжение Draft PR #3, с неизменной оригинальной 4.3 и неизменной Auto
Paper 4.2. Только Strategy Lab. Никаких production Paper/биржевых ордеров,
Supabase, scheduler, balance/position writes, merge или deploy.

## Протокол и ограничения независимости

До скачивания расширенной истории и расчёта новых результатов зафиксирован
`AURA43_PROFILES_PROTOCOL.json`. Три набора параметров заданы заранее, без grid
search и без подгонки по validation. Ни один набор не изменяется по результатам.

Публичный Binance REST, BTCUSDT 15m, **шесть полных календарных месяцев**:
2026-04-16 00:00 — 2026-10-16 00:00 UTC exclusive (183 дня, 17 568 свечей).
Ещё 4 160 свечей прогрева; всего 21 728. Это нижняя граница запрошенных
6–12 месяцев, не годовой и не многорежимный многолетний тест.
Все 12 800 строк пересечения с предыдущим 90-day исследованием совпали точно.

- 70%: первые `floor(17568×7/10) = 12297` свечей, development 128.09375 дня.
- 30%: последние 5271 свеча, validation 54.90625 дня.
- Граница: **2026-08-22 02:15 UTC**. Округление только к закрытой 15m свече.
- Каждый вариант/split — новый изолированный account 10 000 USDT в RAM.
  Позиции/pending/cashflows через границу не переносятся; прошлый warm-up разрешён.
- 14 вариантов × 3 split: native 4.2, original 4.3, три профиля и их девять
  самостоятельных сценариев. Портфели сценариев не суммируются.

**Последние 30% не используются для настройки новых профилей. Однако этот
период пересекается с уже исследованными данными: это не новый blind holdout.**
Полная 6-month строка — описательная; она не ещё одна независимая проверка.
Предыдущие исследования и три новых профиля создают multiple-comparison bias.
Даже положительная validation не доказывает будущую прибыльность.

Выбор только по development: ≥20 закрытых сделок, net>0, PF≥1.1, max DD<10%,
положительна как минимум половина полных календарных development месяцев;
среди допустимых максимальная expectancy. Выбор записывается в отдельный
selection artifact с UTC timestamp/hash **до расчёта validation metrics**.
Если никто не подходит, победитель отсутствует. Нельзя заменить его вариантом,
выглядящим лучше на validation. Проверочные пороги те же; это предзаданный
исследовательский фильтр, а не тест статистической значимости.

## Что изменяют профили

Все используют неизменные EMA20/50, RSI14, ADX14, ATR14 из production context;
формулы индикаторов не меняются. 15m — вход, 1h — основной тренд; 4h — только
контекст RR (2R / 1.75R при встречном направлении), без обязательного MTF veto.

| Фильтр | Conservative | Balanced | Active |
|---|---:|---:|---:|
| ADX1h для TRENDING | 25 | 22 | 20 |
| ADX15m Pullback / Breakout | 20 | 18 | 15 |
| EMA touch tolerance, ATR | .25 | .40 | .50 |
| Pullback confirmation | За wick предыдущей свечи + .05 ATR | За body + .03 ATR | За body + .02 ATR |
| Pullback RSI LONG / SHORT | 45–68 / 32–55 | 42–72 / 28–58 | 40–75 / 25–60 |
| Pullback min volume ratio | .8 | .8 | .7 |
| Breakout prior range bars / max ATR width | 20 / 6 | 16 / 8 | 12 / 10 |
| Breakout min volume / ATR buffer | 1.5 / .10 | 1.25 / .08 | 1.1 / .05 |
| Breakout RSI LONG / SHORT | 55–75 / 25–45 | 52–78 / 22–48 | 50–80 / 20–50 |
| Reversal prior RSI exhaustion | ≤35 / ≥65 | ≤40 / ≥60 | ≤40 / ≥60 |
| Reversal current RSI | 40–60 | 38–62 | 38–62 |
| Reversal confirmed CHoCH lookback | 8 | 8 | 12 |
| Reversal confirmation | Directed retest | Retest или направленный close за prior 3-bar high/low | То же |
| Reversal min volume ratio | 1 | 1 | .9 |

Pullback сохраняет совпадение направлений EMA15m и EMA1h, направленную свечу,
close за EMA20 и запрет явно противоположной HH/HL структуры. Более мягкий
body confirmation всё равно требует пробоя наблюдаемого уровня, не просто
смены цвета. Breakout исключает сильный встречный 1h ADX≥25 во всех профилях.
Reversal требует подтверждённого CHoCH + одноимённого breakout с одним
**прошлым** timestamp; текущий разворот структуры из будущих пивотов запрещён.

HIGH_VOLATILITY (ATR/close ratio≥1.5): только Breakout, volume≥2,
buffer≥.2 ATR во всех профилях. SHOCK bar range>3 ATR исключён.
Приоритет при нескольких кандидатах прежний: Pullback → Breakout → Reversal.
Conservative воспроизводит исходные сигналы/SL/TP 4.3, кроме более подробных
меток отказа. Сравнение его результатов с original — обязательная проверка.

## Риск и исполнение

Неизменённый `app/automated/engine.py`: planned fee-inclusive risk≤0.5%,
daily loss halt 2%, drawdown halt 10%, одна позиция, notional≤2000 USDT,
10 bps fee и 5 bps adverse slippage на сторону. Ограничения никогда не
ослабляются Active. После risk halt состояние PAUSED остаётся latched,
как в production 4.2; исследование его не включает заново на следующий день.

SL по наблюдаемой структуре последних 5/8/12 свечей или breakout level:
минимум 1.2 ATR до .25 ATR буфера, максимум 3 ATR. Close-time net RR≥1.2.
Gap может изменить фактический entry RR; production engine дополнительно
проверяет положительный net reward и fee-inclusive risk, без изменения его
правил. Stop gaps могут превысить плановый риск; halt не гарантирует цену выхода.

Решение использует закрытый prefix 4160–4175 15m свечей, с точным rolling
UTC 4h start production. Все полные higher candles агрегированы по UTC.
Никаких будущих RSI, незавершённых higher candles и future pivot confirmation.
Офлайн cache вычисляет causal prefix states; отдельная проекция возвращает
**те же потребляемые strategy inputs**, что `analyze_window` (включая source
hash, события и alignment). Эта проекция не устанавливается в веб-приложении.

После полной валидации CSV execution engine получает две последовательные
свечи — предыдущую watermark и вновь закрытую; для обработки одного шага это
достаточный и эквивалентный full-window input. Само решение получает полный
production window. Тест сравнивает state/events полного и сокращённого входа.
Это оптимизация офлайн транспорта, не новый торговый движок.

Сигнал после close, fill на следующем bar open обрабатывается только после
закрытия execution bar, как в существующей модели 4.2. Нет fill на signal bar.
Консервативный SL-first при двусмысленном OHLC, adverse stop gaps и TP без
улучшения gap-цены. На конце split — mark оставшейся позиции, не force close.
Short — условная виртуальная экспозиция, без фактического Spot borrow.
Funding/borrow/spread/market impact/сбои Render и Supabase не моделируются.
Это идеализированная next-open OHLC модель, а не доказательство достижимости
исторического open после фактической задержки scheduler/network. Время `+30s`
в replay — контракт freshness/обработки существующего engine; внутрисвечная
цена через 30 секунд неизвестна. Проверка не подтверждает реальные fill цены
на Render и не заменяет отдельное forward наблюдение.

Net profit/return по terminal liquidation equity; WR/PF/Expectancy — по
закрытым сделкам. Fees включают entry открытого остатка. Sharpe не определён
при <20 сделках, <30 полных UTC daily returns или нулевой дисперсии.
Сделок/месяц = закрытые сделки ×30 / фактические дни, не обещанная частота.
Monthly equity changes учитывают открытую позицию; полный календарный месяц
отмечен отдельно, частичные месяцы не участвуют в development selection gate.

## Диагностика фильтров

Для каждого profile/scenario/side считаются все проверенные setup gates:
`failed:` — пересекающиеся отказы, `first:` — первый отказ в фиксированном
порядке, `only_blocker:` — ровно один gate не выполнен, все другие выполнены.
Это раздельные LONG/SHORT проверки; сумма failed может превышать число свечей.
Общий SHOCK/invalid input отражается отдельным GLOBAL счётчиком.
Stop-width / net-RR фильтры проверяются **только после** всех setup gates и
показаны как `plan:` причины. Этот funnel не измеряет причинный вклад фильтра
в прибыльность: удаление gate требует нового development исследования.
В UI фильтры агрегированы по всему периоду и не используются для переотбора
после validation. Полный raw log всех отказов не отдаётся браузеру: все signal
решения + дневная выборка WAIT, с явной маркировкой; счётчики по всем свечам.

## Воспроизведение и публикация

```bash
gzip -dc docs/data/AURA43_PROFILES_BTCUSDT_15m.csv.gz > /tmp/aura43-6m.csv
python -m scripts.research_aura43_profiles --csv /tmp/aura43-6m.csv \
  --output /tmp/aura43-profiles.json.gz --max-seconds 1800
# Если BUDGET_REACHED: повторить точную команду, не менять data/code/protocol.
python -m scripts.audit_aura43_profiles --report /tmp/aura43-profiles.json.gz \
  --csv /tmp/aura43-6m.csv --output /tmp/aura43-profiles-audit.json
python -m pytest -q
for file in tests/*.cjs; do node "$file"; done
```

Повторное скачивание: `python -m scripts.aura43_history --output /tmp/aura43-6m.csv`.
Сверить SHA с provenance: upstream может исправить историю. Loader читает
ограниченный CSV кусками через неизменённый strict importer, проверяет также
межкусковые границы; синтетические свечи не добавляет. REST response hashes
не являются независимой архивной checksum-аттестацией.

В Strategy Lab открыть **Aura 4.3 · Conservative / Balanced / Active**.
Новый owner-only GET `/api/lab/profiles43` и `/api/lab/profiles43/detail` читают
только bounded immutable gzip artifact с code/data/protocol/selection hashes.
Owner auth/no-store, фиксированные variant/split, bounded pagination,
textContent вместо HTML interpolation, никакой activation или POST.
Полный replay запускается офлайн, не внутри Render HTTP handler.

PR зависит от Draft PR #3; его ветка является base для отдельного review diff.
После отдельного разрешения на merge/deploy обычная публикация Render покажет
сохранённый отчёт. Environment Variables/SQL/scheduler менять не требуется.
В этой работе merge/deploy запрещены и не выполняются. Успешный backtest
не подтверждает production autonomous OPEN → CLOSE и не разрешает PAPER.

## Code review и security review

Отдельные проверки по `docs/ecc/TRADING_REVIEW.md`:

- **Code review:** проверены causal prefix/UTC higher alignment, delayed pivot
  events, fixed profile parameters, development-only selection, one-step engine
  equivalence, reset split accounting, monthly equity semantics и RR costs.
  Формулы production и старой 4.3 не изменены. Не обнаружено подтверждённых
  critical/high проблем в новом исследовательском пути.
- **Security review:** новые API только GET, owner/no-store, fixed artifact path,
  hash/size/software checks, ограниченная пагинация/whitelist, thread offload.
  Browser использует textContent, fixed URLs и bounded fetch/abort, не account
  controls. CSV downloader только фиксированный public Binance endpoint,
  redirects off, budget/page limit; loader без приватных клиентов. Поиск
  credential patterns в изменённых/новых текстовых файлах не выявил совпадений;
  реальные credentials не читались и не использовались.
- **Остаточные ограничения:** OHLC моделирование вместо tick fills; modeled
  slippage/fees; отсутствие market impact/funding/borrow; пересечение validation
  с уже изученной историей; multiple comparisons; малая длительность периода;
  дневной risk halt latched, как в 4.2. Артефакт с checksum защищает от случайной
  порчи/устаревания, не является криптографической подписью внешнего источника.

Это самостоятельные review passes, не заявление о внешнем независимом reviewer
или автоматическом security scanner. Успешная проверка не разрешает исполнение.

## Фактические результаты

Источник SHA256: `e9bdc4c401c51ed07f509a7db9a2b20668e954565c5a3dfa2f14796aaa4e6ec9`.

### Development 70%

| Вариант | Сигналы | Сделки | Сделок /30d | Net USDT | Return % | PF | WR % | Max DD % | Expectancy | Fees USDT | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 13 | 11 | 2.5762 | -25.2269 | -0.2523 | 0.8265 | 36.3636 | 1.3314 | -2.2934 | 43.8753 | ON |
| AURA43_ORIGINAL | 26 | 17 | 3.9815 | -108.2571 | -1.0826 | 0.6240 | 29.4118 | 1.8244 | -7.1544 | 70.0952 | ON |
| Conservative | 26 | 17 | 3.9815 | -108.2571 | -1.0826 | 0.6240 | 29.4118 | 1.8244 | -7.1544 | 70.0952 | ON |
| Conservative_TREND_PULLBACK | 16 | 10 | 2.3420 | 89.0561 | 0.8906 | 1.6000 | 50.0000 | 0.7630 | 7.5689 | 41.9805 | ON |
| Conservative_BREAKOUT | 11 | 8 | 1.8736 | -176.1875 | -1.7619 | 0.1353 | 12.5000 | 1.7619 | -22.0234 | 32.0896 | ON |
| Conservative_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Balanced | 47 | 28 | 6.5577 | -298.9495 | -2.9895 | 0.4508 | 25.0000 | 3.6671 | -11.1542 | 113.9081 | ON |
| Balanced_TREND_PULLBACK | 28 | 14 | 3.2788 | 12.8845 | 0.1288 | 0.9979 | 42.8571 | 1.1530 | -0.0345 | 57.9644 | ON |
| Balanced_BREAKOUT | 20 | 16 | 3.7473 | -377.4798 | -3.7748 | 0.0680 | 6.2500 | 3.7748 | -23.5925 | 64.0534 | ON |
| Balanced_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Active | 73 | 31 | 7.2603 | -296.6426 | -2.9664 | 0.5034 | 29.0323 | 4.0827 | -10.0003 | 126.1488 | ON |
| Active_TREND_PULLBACK | 51 | 20 | 4.6841 | -118.1562 | -1.1816 | 0.6608 | 35.0000 | 2.6594 | -6.5762 | 82.1262 | ON |
| Active_BREAKOUT | 26 | 17 | 3.9815 | -375.2193 | -3.7522 | 0.1338 | 11.7647 | 4.3960 | -22.0717 | 68.1443 | ON |
| Active_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |

### Validation 30%

| Вариант | Сигналы | Сделки | Сделок /30d | Net USDT | Return % | PF | WR % | Max DD % | Expectancy | Fees USDT | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| AURA43_ORIGINAL | 2 | 1 | 0.5464 | 27.6996 | 0.2770 | N/A | 100.0000 | 0.0679 | 27.6996 | 3.9683 | ON |
| Conservative | 2 | 1 | 0.5464 | 27.6996 | 0.2770 | N/A | 100.0000 | 0.0679 | 27.6996 | 3.9683 | ON |
| Conservative_TREND_PULLBACK | 1 | 1 | 0.5464 | 27.6996 | 0.2770 | N/A | 100.0000 | 0.0679 | 27.6996 | 3.9683 | ON |
| Conservative_BREAKOUT | 1 | 1 | 0.5464 | -22.8749 | -0.2287 | 0.0000 | 0.0000 | 0.3202 | -22.8749 | 4.0189 | ON |
| Conservative_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Balanced | 5 | 3 | 1.6392 | -18.8776 | -0.1888 | 0.5947 | 33.3333 | 0.3624 | -6.2925 | 11.9684 | ON |
| Balanced_TREND_PULLBACK | 3 | 2 | 1.0928 | 4.3803 | 0.0438 | 1.1878 | 50.0000 | 0.2578 | 2.1901 | 7.9876 | ON |
| Balanced_BREAKOUT | 2 | 2 | 1.0928 | -46.1328 | -0.4613 | 0.0000 | 0.0000 | 0.5908 | -23.0664 | 7.9996 | ON |
| Balanced_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Active | 11 | 6 | 3.2783 | 13.2105 | 0.1321 | 1.1749 | 50.0000 | 0.4303 | 2.2018 | 24.0125 | ON |
| Active_TREND_PULLBACK | 8 | 6 | 3.2783 | 10.7475 | 0.1075 | 1.1423 | 50.0000 | 0.3573 | 1.7913 | 24.0100 | ON |
| Active_BREAKOUT | 3 | 3 | 1.6392 | -13.2863 | -0.1329 | 0.7120 | 33.3333 | 0.5889 | -4.4288 | 12.0365 | ON |
| Active_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |

### Полные 6 месяцев — описательно

| Вариант | Сигналы | Сделки | Сделок /30d | Net USDT | Return % | PF | WR % | Max DD % | Expectancy | Fees USDT | Mode |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 13 | 11 | 1.8033 | -25.2269 | -0.2523 | 0.8265 | 36.3636 | 1.3314 | -2.2934 | 43.8753 | ON |
| AURA43_ORIGINAL | 28 | 19 | 3.1148 | -131.2111 | -1.3121 | 0.6363 | 31.5789 | 1.8244 | -6.9058 | 76.0302 | ON |
| Conservative | 28 | 19 | 3.1148 | -131.2111 | -1.3121 | 0.6363 | 31.5789 | 1.8244 | -6.9058 | 76.0302 | ON |
| Conservative_TREND_PULLBACK | 17 | 12 | 1.9672 | 66.1020 | 0.6610 | 1.4045 | 50.0000 | 0.7630 | 5.5085 | 47.9155 | ON |
| Conservative_BREAKOUT | 12 | 9 | 1.4754 | -199.0624 | -1.9906 | 0.1216 | 11.1111 | 1.9906 | -22.1180 | 36.1084 | ON |
| Conservative_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Balanced | 52 | 32 | 5.2459 | -368.4808 | -3.6848 | 0.4353 | 25.0000 | 3.7286 | -11.5150 | 127.8432 | ON |
| Balanced_TREND_PULLBACK | 31 | 17 | 2.7869 | -33.3889 | -0.3339 | 0.8848 | 41.1765 | 1.1530 | -1.9641 | 67.9187 | ON |
| Balanced_BREAKOUT | 22 | 18 | 2.9508 | -423.6126 | -4.2361 | 0.0611 | 5.5556 | 4.2361 | -23.5340 | 72.0529 | ON |
| Balanced_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |
| Active | 84 | 37 | 6.0656 | -307.5914 | -3.0759 | 0.5671 | 32.4324 | 4.0827 | -8.3133 | 148.1505 | ON |
| Active_TREND_PULLBACK | 59 | 26 | 4.2623 | -131.5680 | -1.3157 | 0.7225 | 38.4615 | 2.6594 | -5.0603 | 104.1255 | ON |
| Active_BREAKOUT | 29 | 20 | 3.2787 | -388.5056 | -3.8851 | 0.1895 | 15.0000 | 4.3960 | -19.4253 | 80.1807 | ON |
| Active_REVERSAL | 0 | 0 | 0.0000 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | 0.0000 | ON |

### Зафиксированный отбор

Статус: **NO_ROBUST_ADVANTAGE**. Выбор только по development: **None**.

Selection hash: `c741955db69e68cdc11dd676d4e4dfa2f30db424a32d725f5a2372070b9ae787`; UTC seal: `2026-10-16T17:40:51.680506+00:00`.

### Какие фильтры блокировали входы

| Профиль | Сценарий | Главные единственные setup blockers (LONG+SHORT) | Plan blockers после setup |
|---|---|---|---|
| Conservative | TREND_PULLBACK | entry_confirmation: 390, ema_direction: 228, volume: 159, adx: 111 | COST_ADJUSTED_RR_TOO_LOW: 120, STRUCTURE_STOP_TOO_WIDE: 13 |
| Conservative | BREAKOUT | entry_confirmation: 640, adx: 171, volume: 164, h1_context: 76 | COST_ADJUSTED_RR_TOO_LOW: 253, STRUCTURE_STOP_TOO_WIDE: 1 |
| Conservative | REVERSAL | entry_confirmation: 20, rsi_exhaustion: 11, volume: 10, regime: 8 | COST_ADJUSTED_RR_TOO_LOW: 2 |
| Balanced | TREND_PULLBACK | entry_confirmation: 600, ema_direction: 530, volume: 384, ema_touch: 230 | COST_ADJUSTED_RR_TOO_LOW: 285, STRUCTURE_STOP_TOO_WIDE: 38 |
| Balanced | BREAKOUT | entry_confirmation: 1589, volume: 240, adx: 191, h1_context: 142 | COST_ADJUSTED_RR_TOO_LOW: 439, STRUCTURE_STOP_TOO_WIDE: 1 |
| Balanced | REVERSAL | structure: 241, regime: 40, volume: 33, entry_confirmation: 28 | STRUCTURE_STOP_TOO_WIDE: 14, COST_ADJUSTED_RR_TOO_LOW: 5 |
| Active | TREND_PULLBACK | entry_confirmation: 1153, ema_direction: 911, volume: 432, ema_touch: 329 | COST_ADJUSTED_RR_TOO_LOW: 514, STRUCTURE_STOP_TOO_WIDE: 93 |
| Active | BREAKOUT | entry_confirmation: 2500, volume: 406, h1_context: 230, adx: 142 | COST_ADJUSTED_RR_TOO_LOW: 742, STRUCTURE_STOP_TOO_WIDE: 2 |
| Active | REVERSAL | structure: 241, regime: 80, entry_confirmation: 57, volume: 42 | STRUCTURE_STOP_TOO_WIDE: 28, COST_ADJUSTED_RR_TOO_LOW: 7 |

Пустая ячейка означает отсутствие такого наблюдения. only_blocker не включает
последующий stop/RR gate, если setup не прошёл. Полные failed/first/global
счётчики с знаменателем evaluated доступны в UI и JSON artifact.

### Помесячная проверочная устойчивость общих профилей

| Вариант | Месяц | Closed trades | Изменение equity USDT | Полный календарный месяц |
|---|---|---:|---:|---|
| AURA42 | 2026-08 | 0 | 0.00000000 | False |
| AURA42 | 2026-09 | 0 | 0.00000000 | True |
| AURA42 | 2026-10 | 0 | 0.00000000 | False |
| AURA43_ORIGINAL | 2026-08 | 0 | 0.00000000 | False |
| AURA43_ORIGINAL | 2026-09 | 0 | 0.00000000 | True |
| AURA43_ORIGINAL | 2026-10 | 1 | 27.69964360 | False |
| Conservative | 2026-08 | 0 | 0.00000000 | False |
| Conservative | 2026-09 | 0 | 0.00000000 | True |
| Conservative | 2026-10 | 1 | 27.69964360 | False |
| Balanced | 2026-08 | 1 | -23.25783897 | False |
| Balanced | 2026-09 | 0 | 0.00000000 | True |
| Balanced | 2026-10 | 2 | 4.38025089 | False |
| Active | 2026-08 | 3 | 34.55344131 | False |
| Active | 2026-09 | 1 | -25.72316214 | True |
| Active | 2026-10 | 2 | 4.38025089 | False |

N/A — неопределённая метрика (например, нет убыточных сделок для PF),
не нулевая доходность. Все исходные trades, fees, slippage, daily equity и
scenario attribution доступны в compressed artifact. Сигнал не равен сделке:
действуют одна позиция, risk halt и next-open validation.

## Вывод и ответы на вопросы

**NO_ROBUST_ADVANTAGE. Лучший пригодный к запуску профиль не найден.**
Все общие профили убыточны на development и за полные шесть месяцев; ни один
не прошёл зафиксированный development gate. Снижение частоты отказов увеличило
число сделок, но не подтвердило качество. Относительно оригинальной 4.3 /
Conservative (19 сделок) Balanced дал 32, Active — 37. Все остались в ON до
конца: редкость входов здесь не объясняется ранним latched risk halt.

1. **Какой вариант лучший?** Нет допустимого победителя. Conservative имеет
   наименьший полный убыток среди профилей (−131.21 USDT), но это относительное
   описание убыточного результата, не рекомендация. Не выбираем Active по его
   положительным шести validation сделкам после провала development.
2. **Сделок в месяц:** Conservative 3.11, Balanced 5.25, Active 6.07 в среднем
   на 30 дней полного периода. На validation — 0.55 / 1.64 / 3.28 соответственно.
   Частота сильно зависит от периода и не гарантирована на будущее.
3. **Доходность после комиссий/slippage:** −1.3121% / −3.6848% / −3.0759%
   за шесть месяцев. Validation: +0.2770% / −0.1888% / +0.1321%, всего
   1 / 3 / 6 сделок. Положительные строки не дают достаточных доказательств.
4. **Max DD:** 1.8244% / 3.7286% / 4.0827% за полный период. Низкая наблюдаемая
   просадка не означает низкий tail risk или прибыльность; все результаты net<0.
5. **Достаточно для PAPER?** Нет для запуска как подтверждённо улучшенной
   стратегии. На validation мало сделок, нет допустимого development кандидата,
   проверка не blind. Оставить только Strategy Lab; новые исследования/forward
   наблюдение требуют нового заранее определённого протокола, без обещания edge.
6. **Устойчивое преимущество?** Не показал ни один профиль. Параметры после
   результатов не ослаблялись. Ранние +38.82 за 90 дней не обобщились на 6 месяцев.

Главные ограничения частоты: подтверждение входа и volume/RSI/structure gates.
Среди уже прошедших setup часто блокирует **net RR после издержек**:
375 / 729 / 1263 отказа планов для Conservative / Balanced / Active.
Этот экономический фильтр не снимался. Часть Reversal setup дошла до плана,
но ни один не прошёл stop-width/net-RR: реальных сигналов/сделок Reversal нет.
Нельзя объявлять его рабочим по положительному синтетическому unit fixture.
Breakout ухудшил результаты; более частый вход сам по себе не был улучшением.

Число сделок полного периода может отличаться от суммы development+validation:
в отдельных split позиции на границе не переносятся и не закрываются насильно.
В development имеется незакрытая позиция, отражённая в liquidation equity;
её будущее закрытие не используется для development selection. Отчёт показывает
эту позицию отдельно. В конце full и validation у общих профилей позиций нет.

## Итоговые проверки

- **1222 Python tests passed**, 1 upstream Starlette/AnyIO deprecation warning,
  166.96 s. Cloud-specific poll workaround использован только в test runner.
- **18 JavaScript suites passed**, включая новые profile UI проверки.
- `AURA43_PROFILES_ACCOUNTING_AUDIT.json`: PASS, **42 прогона, 435 записей
  сделок** (повторения full/split/сценариев; не 435 уникальных сделок).
  Независимый Decimal-64 oracle проверил OHLC first touch, gap/SL-first,
  fee/slippage, sizing/risk/notional, balance/PnL, daily equity и **все bar
  open/close equity marks и Max DD**, а не только точки отображаемой кривой.
- `AURA43_PROFILES_CAUSAL_AUDIT.json`: PASS, **17 568 решений** — Conservative
  полностью совпал с original 4.3 по сигналам/SL/TP; **32 реальных cutoff**
  всех UTC фаз в development/validation совпали с production snapshot inputs;
  изменение будущих цен не изменило prefixes. Выбор пересчитан только из dev.
- Artifact reader: actual checksum/code hashes, 42 summary rows и detail
  pagination проверены. Старый 90-day artifact по-прежнему доступен.
- Python AST/import, JavaScript syntax, git whitespace, read-only owner API,
  no-production-import checks passed. Защищённые production paths и scheduler
  неизменны относительно main; original 4.3 и предыдущий отчёт неизменны.
- Никаких подключений/записей реального Supabase, изменений balance/positions,
  ордеров, merge или Render deploy.

Правила/код закреплены коммитом `e9e6771` до расчёта validation метрик;
selection hash выше записан до validation. Это внутренний воспроизводимый
протокол, не внешняя preregistration или независимая аттестация прибыльности.

Отдельно: Conservative Pullback-only показал +66.10 USDT за 12 закрытых
сделок, PF 1.4045, Max DD 0.7630%. Это самый интересный **описательный** сценарий,
но не прошедший development отбор общий профиль: dev содержит всего 10 закрытий,
validation — одно. Нельзя задним числом объявить его выбранным победителем или
обойти отсутствие статистики, исключив убыточный Breakout после проверки.

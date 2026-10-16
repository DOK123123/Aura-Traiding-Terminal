# Aura 4.3 Adaptive — Strategy Lab only

Версия правил `AURA43_RESEARCH_1`. Базовая main:
`c50fd0bb2402bd261089142c96d4e9981f4594ab`. Никакого автоматического включения,
merge/deploy, изменения production account или реальных биржевых ордеров.

## Изоляция и архитектура

Новый модуль `app/lab/adaptive43.py` вычисляет независимые предложения по трём
сценариям. Его не импортируют production controller, scheduler или Paper API.
`scripts/research_aura43.py` исполняет только офлайн исследование, вызывая
**неизменённые pure функции** `app/automated/engine.py`. Service/configured,
account storage, Supabase и private exchange clients не используются.

Это отдельное сравнение **Auto Paper 4.2** с 4.3; прежняя строка
`AURA_EXISTING / INCOMPATIBLE` в legacy Lab относится к более старому
fixed-horizon historical-pattern движку и остаётся без изменений. Нельзя
подменить его общим Lab симулятором: там другие risk/execution semantics.
Новая пара сравнивается на одном production 4.2 Decimal engine без такой подмены.

Не изменены production strategy/engine/service/storage, ADX, risk policy,
позиции/баланс, комиссия/slippage, Binance source, Supabase schema/RPC,
GitHub/Cloudflare scheduler и исторические аналоги. Lab API добавляет только GET
заранее рассчитанного отчёта. Нового activation endpoint или Paper кнопки нет.

## Зафиксированные правила

Полный протокол: `AURA43_PROTOCOL.json`. Он и правила сохранены до запуска
расчёта; никакой parameter search, отбора по validation или повторной подгонки
после просмотра результатов не выполнялось.

- 15m — вход; 1h — основной тренд EMA20/50 и ADX14. 4h — контекст:
  при встречном направлении плановый target 1.75R вместо 2R, но нет обязательного
  совпадения направлений всех TF. Будущий/устаревший 4h контекст игнорируется.
- HIGH_VOLATILITY: ATR/close относительно медианы предыдущих 64 значений ≥1.5;
  разрешён только Breakout с volume ratio≥2 и buffer 0.2 ATR.
- TRENDING: известное направление 1h и ADX1h≥25; Pullback или Breakout.
- RANGING: остальные слабые/неопределённые тренды, операционная категория,
  а не доказанная статистическая стационарность; Breakout или Reversal.

**Trend Pullback:** 15m/1h направлены одинаково; ADX15m≥20; предыдущая свеча
касается зоны EMA20/50 ±0.25 ATR, текущая направленным телом закрывается за
предыдущим high/low на 0.05 ATR и за EMA20. RSI LONG 45–68 / SHORT 32–55,
volume ratio≥0.8, нет подтверждённой противоположной HH/HL структуры.

**Breakout:** close за диапазоном **предыдущих** 20 свечей на 0.1 ATR,
ширина диапазона≤6 ATR, volume ratio≥1.5, ADX15m≥20,
RSI LONG 55–75 / SHORT 25–45. Сильный встречный 1h тренд исключён.
В HIGH_VOLATILITY действуют более строгие параметры выше.

**Reversal:** только RANGING; экстремум RSI≤35 / ≥65 в предыдущих 8 свечах,
текущий RSI 40–60 и разворачивается; подтверждённый CHoCH и направленный breakout
с одним timestamp в предыдущих 8 барах, текущий directed retest, volume ratio≥1.
Пивоты берутся из причинного production context, с задержкой подтверждения.

Для всех сценариев range текущей свечи≤3 ATR; stop за наблюдаемой структурой
последних 5/8 свечей либо уровнем breakout, с минимумом 1.2 ATR до буфера
0.25 ATR; stop шире 3 ATR исключён. Ожидаемый net reward/risk при close с
модельными издержками≥1.2. Это оценка перед next-open, не гарантия после gap.
При одновременных кандидатах порядок фиксирован: Pullback → Breakout → Reversal.
Сценарии также тестируются как три самостоятельных портфеля, не суммируются.

## Реальные данные и протокол сравнения

Источник: фиксированный Binance Spot public REST `/api/v3/klines`, BTCUSDT 15m.
**12800 реальных свечей**, с 2026-06-04 16:00 до 2026-10-16 00:00 UTC exclusive.
4160 свечей — прогрев; 8640 — ровно 90 дней оценки.
Период оценки: **2026-07-18 — 2026-10-16 UTC**.

- Development: 2026-07-18 — 2026-09-16, 60 дней.
- Validation: 2026-09-16 — 2026-10-16, 30 дней.
- Full 90d — только описательная общая строка, не ещё один независимый тест.

CSV SHA256: `f38de999503bfa7f5b8bc8857752a04c6d08b271be9e5025cdf60d74a2c6569b`.
Оригинальные строки с LF: `data/AURA43_BTCUSDT_15m.csv.gz`.
REST acquisition time, queries и response hashes: `data/AURA43_DATA_PROVENANCE.json`.
Строгий существующий importer проверил OHLCV, timestamps, close times,
монотонность, отсутствие дублей/разрывов и будущих свечей. Это REST provenance,
не независимая аттестация checksum месячного Binance ZIP. Синтетических данных
в историческом исследовании нет; synthetic fixtures применяются только в unit tests.

Validation отделена хронологически и не используется для выбора параметров.
Однако части 2026 года уже изучались в предыдущих исследованиях, поэтому это
**не нетронутый blind holdout**. Для утверждения о преимуществе нужна новая
forward validation и более длинная проверка нескольких режимов рынка.

## Исполнение, риск и метрики

Начало каждого из пяти вариантов и каждого split: отдельный RAM account
**10000 USDT**, без переноса позиции или pending через границу split. Индикаторам
доступна только предшествующая история, включая warm-up до validation.
Риск≤0.5% **с учётом stop slippage и entry/exit fees**, notional≤2000, одна
позиция, daily-loss 2%, max-DD 10%. Сохраняется прежняя latched PAUSED семантика
4.2 при risk halt: исследование не возобновляет её автоматически на следующий день.

Комиссия 10 bps и adverse slippage 5 bps **на каждую сторону** у обоих вариантов.
Сигнал после close; исполнение next-bar open фиксируется после закрытия этого
бара, как в существующей Auto Paper модели. Нет same-close или same-bar leakage.
SL-first при неоднозначном OHLC, adverse stop gaps и conservative TP gaps.
Funding/borrow/spread/market impact не моделируются. SHORT — условная
направленная виртуальная экспозиция, не фактический Binance Spot borrow.

На границе выборки позиция не закрывается искусственно. Net profit/Return
используют liquidation equity с незакрытой позицией; realized PnL отдельно.
Win Rate/PF/average win/loss/expectancy — только закрытые сделки; average loss
показан положительной величиной убытка. Fees — фактически начисленные модельные
fees, включая entry оставшейся позиции. Equity учитывает также оценку будущего
exit fee незакрытой позиции. Sharpe: полные UTC daily equity returns,
sample stdev, sqrt(365), нулевая RF; не определён при <20 сделках, <30 returns
или нулевой дисперсии. Max DD — прежняя engine liquidation-equity метрика.
Из-за gap фактический stop loss может превысить плановые 0.5% и пределы halt.

## Воспроизведение и интерфейс

```bash
gzip -dc docs/data/AURA43_BTCUSDT_15m.csv.gz > /tmp/aura43.csv
python -m scripts.research_aura43 --csv /tmp/aura43.csv \
  --output /tmp/aura43-result.json.gz --workers 2 --max-seconds 1800
# При budget limit повторить точную команду: checkpoint связан с data/code/protocol.
python -m scripts.audit_aura43 --report /tmp/aura43-result.json.gz \
  --csv /tmp/aura43.csv --output /tmp/aura43-audit.json
python -m pytest -q
node tests/test_adaptive43_frontend.cjs
```

Для повторного публичного скачивания: `python -m scripts.fetch_aura43_history
--output /tmp/aura43.csv`. Сверить dataset SHA, поскольку upstream может
скорректировать историю. Исследование запускается **офлайн**, не внутри Render
HTTP request. Native PrefixCache применяется только в отдельных research
процессах, не устанавливается в production MarketContext.

В Strategy Lab открыть **Aura 4.2 ↔ Aura 4.3 Adaptive · 90-day research**.
Кнопка читает сохранённый checksum/code-hash-bound artifact; GET
`/api/lab/adaptive43` и `/api/lab/adaptive43/detail` требуют owner auth/no-store.
Показаны пять вариантов, full/development/validation, overlay equity,
история сделок и причины strategy/execution отказов с пагинацией.
Параметры/risk старого Lab ниже относятся к прежним baseline studies, не к этой
отдельной проверке. Нет кнопки активации и нет записи в Paper/Supabase.
При отсутствии/повреждении отчёта или изменении кода данные не заменяются
выдуманными результатами: показывается явная ошибка.

После одобрения merge/deploy UI может быть опубликован обычным Render
процессом. Environment Variables/SQL/scheduler менять не требуется.
Само объединение этого research PR **не включает Aura 4.3** в Auto Paper.
В данной сессии merge/deploy не выполняются.

## Фактические результаты (зафиксированы без последующей подгонки)

### Полные 90 дней

| Вариант | Сделки | Net USDT | Return % | WR % | PF | Max DD % | Avg win | Avg loss | Expectancy | Sharpe | Fees USDT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 4 | -22.7651 | -0.2277 | 25.0000 | 0.6075 | 0.6908 | 35.2286 | 19.3312 | -5.6913 | N/A | 15.9932 |
| AURA43_ADAPTIVE | 3 | 38.8228 | 0.3882 | 66.6667 | 2.0412 | 0.6844 | 38.0545 | 37.2863 | 12.9409 | N/A | 11.9875 |
| AURA43_TREND_PULLBACK | 3 | 38.8228 | 0.3882 | 66.6667 | 2.0412 | 0.6844 | 38.0545 | 37.2863 | 12.9409 | N/A | 11.9875 |
| AURA43_BREAKOUT | 1 | -22.8749 | -0.2287 | 0.0000 | 0.0000 | 0.3202 | N/A | 22.8749 | -22.8749 | N/A | 4.0189 |
| AURA43_REVERSAL | 0 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | N/A | N/A | N/A | 0.0000 |

### Development 60 дней

| Вариант | Сделки | Net USDT | Return % | WR % | PF | Max DD % | Avg win | Avg loss | Expectancy | Sharpe | Fees USDT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 4 | -22.7651 | -0.2277 | 25.0000 | 0.6075 | 0.6908 | 35.2286 | 19.3312 | -5.6913 | N/A | 15.9932 |
| AURA43_ADAPTIVE | 2 | 11.1232 | 0.1112 | 50.0000 | 1.2983 | 0.6844 | 48.4094 | 37.2863 | 5.5616 | N/A | 8.0191 |
| AURA43_TREND_PULLBACK | 2 | 11.1232 | 0.1112 | 50.0000 | 1.2983 | 0.6844 | 48.4094 | 37.2863 | 5.5616 | N/A | 8.0191 |
| AURA43_BREAKOUT | 0 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | N/A | N/A | N/A | 0.0000 |
| AURA43_REVERSAL | 0 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | N/A | N/A | N/A | 0.0000 |

### Validation 30 дней

| Вариант | Сделки | Net USDT | Return % | WR % | PF | Max DD % | Avg win | Avg loss | Expectancy | Sharpe | Fees USDT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AURA42 | 0 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | N/A | N/A | N/A | 0.0000 |
| AURA43_ADAPTIVE | 1 | 27.6996 | 0.2770 | 100.0000 | N/A | 0.0679 | 27.6996 | N/A | 27.6996 | N/A | 3.9683 |
| AURA43_TREND_PULLBACK | 1 | 27.6996 | 0.2770 | 100.0000 | N/A | 0.0679 | 27.6996 | N/A | 27.6996 | N/A | 3.9683 |
| AURA43_BREAKOUT | 1 | -22.8749 | -0.2287 | 0.0000 | 0.0000 | 0.3202 | N/A | 22.8749 | -22.8749 | N/A | 4.0189 |
| AURA43_REVERSAL | 0 | 0.0000 | 0.0000 | N/A | N/A | 0.0000 | N/A | N/A | N/A | N/A | 0.0000 |

N/A означает отсутствие достаточных наблюдений/знаменателя, не нулевую доходность.
Sharpe не публикуется: ни один вариант не достиг заранее установленного минимума
20 закрытых сделок. В конце всех 15 прогонов нет открытых или pending позиций.
Все значения в таблицах описательные, не статистическое доказательство.

**Цель большей частоты не достигнута:** 4.3 дала 4 сигнала и 3 сделки,
4.2 — 6 сигналов и 4 сделки. После fees/slippage net улучшился с −22.7651
до +38.8228 USDT, но основан всего на трёх сделках. Max DD 4.3 = 0.68436805%,
4.2 = 0.69084783%; такая разница не подтверждает снижение риска.

Из самостоятельных сценариев Pullback: 3 сделки, +38.8228 USDT;
Breakout: 1 сделка, −22.8749 USDT; Reversal: 0 сигналов/сделок, оценить нельзя.
В общем Adaptive breakout был отклонён из-за уже открытого Pullback;
портфели сценариев нельзя складывать. На validation общий Adaptive имеет
лишь одну прибыльную сделку (+27.6996), baseline — ни одной. Это не позволяет
сделать надёжный вывод о преимуществе на независимых данных.

**Рекомендация:** оставить 4.3 исключительно в Strategy Lab. Не включать её
в текущий Auto Paper. 90 дней и 3 сделки недостаточны; нужен новый, более
длинный независимый период и отдельное наблюдение без ордеров. Параметры после
результатов не ослаблялись. Этот PR не доказывает автономный live OPEN → CLOSE.
Ранее сообщённые 5 закрытых сделок относятся к другому периоду/запуску;
здесь не подменены ими результаты точно указанного 90-day dataset.

## Проверки и границы доказательства

- Все Python тесты: **1211 passed**, 1 upstream deprecation warning, 98.04 s.
- Все JavaScript наборы: **17 passed**, включая 3 новых frontend проверки.
- Отдельный независимый Decimal-64 accounting audit: **PASS**, 15 прогонов,
  22 записи сделок (с повторением full/split/scenario, не 22 уникальные сделки).
  Проверены dataset SHA, календарные/торговые границы, fills, fees/slippage,
  баланс, риск, отсутствие перекрытия позиций, PnL и агрегаты.
- Unit tests: все три LONG сценария, причинность/будущие и незакрытые свечи,
  пропуски/устаревание, 4h context, волатильность, риск и duplicate protection,
  owner auth, artifact tampering/software mismatch, отсутствие write endpoints.
- Production code paths, historical analog data и scheduler неизменны относительно
  main c50fd0b. Supabase не подключался и не изменялся; только публичный REST
  исторических свечей. Никаких реальных или production Paper ордеров.

Машиночитаемый отчёт: `AURA43_COMPARISON.json.gz`; независимая проверка:
`AURA43_ACCOUNTING_AUDIT.json`. Equity chart использует ограниченную выборку
точек; Max DD рассчитывается engine по всем барам, не по нарисованным точкам.

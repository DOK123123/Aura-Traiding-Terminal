# Независимая проверка исполнения — PASS

Scope: новый offline runner, неизменный AURA ANALYST и чистые денежные helpers
старого Lab. Не production, не брокерское исполнение и не прибыльность.

## Совместимость

- `app/lab/execution.fee/fill/metrics` и Decimal `money/text` совместимы в рамках
  unlevered linear USDT-модели. Проверены независимой арифметикой в тестах.
- Полный `app/lab/execution.simulate` **не совместим** с absolute Entry-zone/
  SL/TP/availability/TTL/guard семантикой ANALYST. Это не объявление старой
  relative-distance модели ошибочной; это разные контракты. Рабочий Lab не менялся.
- Отдельный execution loop добавляет только недостающую семантику, используя
  проверенные accounting primitives. `Baseline.risk_pct` старого Lab не является
  источником новых ограничений: новый Config отдельно требует ≤0.5%.

## Независимые известные ответы

Искусственная котировка 100, fee=10bps/side, slip+half-spread=6bps/side,
fixture tick=.0001. Per-unit линейный расчёт (не реальные результаты BTC):

| Сценарий | Entry fill | Exit fill | Net за 1 условную единицу |
|---|---:|---:|---:|
| LONG TP115 | 100.0600 | 114.9310 | 14.656009 |
| LONG SL95 | 100.0600 | 94.9430 | −5.312003 |
| SHORT TP85 | 99.9400 | 85.0510 | 14.704009 |
| SHORT SL105 | 99.9400 | 105.0630 | −5.328003 |

Тесты независимо умножают эти fills на автоматически выбранную qty, округляют
fees вверх и gross PnL до 8 знаков, затем проверяют cash identity. Reference
не вызывает функции основного расчёта для построения ожидаемого результата.
WR/PF/Expectancy/DD проверены отдельным известным рядом PnL [10, −5, 0].

## Матрица проверок

| Проверка | Результат |
|---|---|
| LONG/SHORT TP, SL, both-touch → SL-first | PASS |
| Adverse gap хуже stop, favorable gap не лучше TP | PASS |
| Entry не использует pre-entry high/low, raw+filled entry-zone | PASS |
| Fee/slippage/spread, fees-inclusive risk, balance identity | PASS |
| Номинал, lot/min-size, margin, остаток дневного бюджета | PASS |
| Daily loss / drawdown latch, stop/guard exits | PASS |
| Нулевой объём, нет сигнала → нет fill | PASS |
| Duplicate ID игнорируется, конфликт ID блокируется | PASS |
| TTL не растягивается: 5m open expired, 1m open допускается | PASS |
| Поздно доступная 4h исключается из анализа | PASS |
| Future append не меняет prefix signals/IDs/equity | PASS |
| Rerun/restart с теми же immutable inputs идентичен | PASS |
| Повторный output не изменяется, hashes артефактов сходятся | PASS |
| Original ANALYST → OPEN → TP → PnL, LONG и SHORT | PASS, SYNTHETIC ONLY |
| Источник/checksum/schema/gaps/duplicates/future availability | PASS |
| Нет network/engine/store/web routes/Render runner | PASS |
| Реальная история: один LONG → SL, CSV и fees | PASS, HISTORICAL MODEL |
| Реальный Render / Supabase / production PAPER | NOT TESTED / NOT TOUCHED |
| Funding и L2 fills, liquidation/плечо >1 | NOT MODELED |
| Независимое прибыльное преимущество | INSUFFICIENT_EVIDENCE |

## Исправленные дефекты при разработке нового стенда

- Разделены native candle close, observed/assumed availability и следующий
  admissible open; coarse 5m TTL mismatch не маскируется продлением сценария.
- Прошлый signal ID не зависит от future-file hash. Обновления будущего датасета
  не создают новый ID для той же закрытой 5m-свечи; конфликт уровней fail-closed.
- Slippage не может сам «создать» касание зоны, если raw OPEN вне зоны.
- Drawdown сохраняет closing peak перед opening gap; daily returns отдельно
  deduplicate равные UTC timestamps, чтобы не подменить денежную просадку.
- Проверены абсолютные, а не заново привязанные stop/target; дневной remaining
  budget дополнительно ограничивает вход. Гэп-убытки не обрезаются задним числом.
- Исправлена исходная календарная конечная граница по фактическим epoch-данным:
  именование файлов UTC+8 не превращалось в сдвиг свечей. Первая попытка BLOCKED
  до вычисления PnL, параметры стратегии/стоимости не подбирались.

Все исправления только в новом исследовательском коде. Источники и strategy
files не модифицировались; не было перестройки стратегии ради получения сделки.
Полный исторический replay после финальных правок сохранил тот же 1 LONG / SL.

## Оставшиеся ограничения

Risk guards наблюдают minute OPEN; гипотетические защитные SL/TP по минутному
OHLC предполагают активную защиту и не моделируют пропуски production scheduler.
Не доказаны публикационные задержки, исторические лоты, полный funding, bid/ask
или фактический fill. Закрытие в конце сегмента — settlement estimate.
`slippage_usdt` / `total_slippage_usdt` — совместимый alias старого Lab для
**суммарного adverse execution impact (slip + spread + tick rounding)**, не
отдельно измеренное проскальзывание. Entry/exit impact уже содержится в PnL.

Default полный локальный regression: **1929 Python PASS, 3 SKIPPED** (opt-in
PostgreSQL, не считаются PASS); **279 JS PASS**. Новые suites: **36 PASS**.
GitHub Regression CI проверяется отдельно на точном SHA PR; зелёный pipeline
не является production/торговой верификацией.

Нулевой объём execution-бара используется только как ретроспективное отсутствие
торгуемых prints для модели fill, не как предиктор сигнала/размера. Время
первой сделки внутри минуты неизвестно; fill на minute OPEN и датировка отказа
— допущения OHLC-модели, не доказательство доступности bid/ask в эту секунду.

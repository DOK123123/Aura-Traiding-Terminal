# Aura Historical Pattern: сентябрь 2026, BTCUSDT / 15m

## Фактически выполненный прогон

Статус **COMPLETE**. Реальный пользовательский CSV был прочитан; Binance API
не запрашивался. Обработаны все 2880 закрытых свечей с open UTC в диапазоне
`[2026-09-01 00:00, 2026-10-01 00:00)`. Production signal был вычислен для
каждой свечи. Синтетические свечи использованы только в unit tests, не в прогоне.

Файл: `BTCUSDT-15m-2026-05_to_09.csv`, 2 367 734 байта, **14 688 свечей**,
12 колонок, без заголовка, timestamps в **микросекундах**.
Охват: `[2026-05-01 00:00, 2026-10-01 00:00)` UTC.
OHLCV, close_time, типы дополнительных колонок, порядок, дубликаты и интервалы
проверены существующим импортёром. Пропусков и дубликатов нет.
Заявленное происхождение — Binance; подлинность файла не сверялась через сеть.

SHA256 исходного CSV:
`cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`.

Ровно **10 000** свечей от `2026-05-19 20:00` до `2026-09-01 00:00` UTC
использованы только как прогрев. Предыдущие 1808 строк файла исключены.
Итого selected dataset — **12 880** свечей. Виртуальный ledger создан пустым
на границе сентября; сделок и денежных потоков прогрева в результатах нет.
Первый сигнал computed на close `2026-09-01 00:15`, последний — на close
`2026-10-01 00:00` (свеча open `2026-09-30 23:45`).

## Результаты

| Показатель | Результат |
| --- | ---: |
| Обработано сентябрьских свечей | 2880 |
| Подтверждённых LONG / SHORT / WAIT | 0 / 0 / 2880 |
| Открыто / закрыто сделок | 0 / 0 |
| Незакрытых позиций | 0 |
| Комиссии фактически начислены | 0 USDT |
| Чистый realized PnL после комиссий | 0 USDT / 0% начального баланса |
| Equity return | 0% |
| Итоговый баланс / equity | 10 000 / 10 000 USDT |
| Максимальная просадка | 0 USDT / 0% |
| Win rate | Не определён: сделок нет |
| Profit factor | Не определён: прибыли/убытков сделок нет |

Список сделок пуст (`trades=[]`); первые пять подтверждённых сигналов тоже
отсутствуют. Нулевой PnL и нулевая просадка отражают отсутствие экспозиции,
а не доказательство прибыльности, качества или безопасности стратегии.

## Почему входов нет

Все 2880 решений Auto — `NO_SIGNAL`: успешный результат стратегии **WAIT**.
Это не `SIGNAL_UNAVAILABLE`, не пропуск вычисления и не ошибка импорта.
Production evaluator был вызван 2880 раз; диагностический observer проверил
согласие объяснения фильтров с действительным production LONG/SHORT/WAIT.

| Невыполненный production filter | Свечей |
| --- | ---: |
| MINIMUM_SAMPLE: минимум 20 аналогов | 2880 |
| CONFIDENCE: raw score минимум 40 | 2880 |
| WILSON: нижняя граница 95% >50% | 2880 |
| DIRECTIONAL_RATE: направленные исходы ≥60% | 2865 |
| EXPECTED_MOVE_COST: направленное среднее >0.05% | 2866 |
| HORIZON_CONSISTENCY: согласованность ≥0.5 | 2865 |
| MEDIAN_DIRECTION: направленная медиана >0 | 2865 |

Счётчики пересекаются: одна WAIT-свеча может не пройти несколько фильтров.
Их нельзя суммировать как число независимых отклонённых входов.
В 2865 случаях не было ни одного выбранного аналога. В оставшихся 15 были
аналоги с предварительной ориентацией LONG (12) или SHORT (3), но ни разу
не набралось 20. Эти ориентации **не являются торговыми сигналами**.
Количество кандидатов, отброшенных similarity/purging, не реконструировалось
и не выдаётся за измеренный результат. Порог similarity сохранён: 75%.

Отказов Paper risk/SL/TP/source/timeframe/position limits: **0** — до проверки
входа не дошёл ни один подтверждённый LONG/SHORT. Это не доказывает, что
любая гипотетическая сделка прошла бы риск. Технические отказы signal reader,
stale data, missing candles, snapshot mismatch: **0** в выполненном прогоне.

## Неизменённая конфигурация и исполнение

Production revision до диагностического адаптера:
`9dfe1ed5fa6160a0b8468b8c82e11daeaba45e74`.
Signal strategy version: `HISTORICAL_PATTERN_V1_DEFAULTS`.
Все production файлы и diagnostic scripts имеют SHA256 в JSON.

`PatternConfig()` без изменений: lookback20, context500, max_matches100,
minimum_similarity75, signal_threshold60, minimum_sample20,
minimum_confidence40, horizons5/10/20/50, decision_horizon20,
round_trip_cost_bps5. Последнее — production фильтр ожидаемого движения;
это не комиссия Paper и оно намеренно не подменялось.

Сценарий **defaults, настройки Render не проверены**:
10000 USDT, risk1%, maximum notional2000 USDT, maximum simultaneous1,
fee0.10% per side, SL2%, TP4%, явный `PAPER_SETTINGS`.
Использованы production SignalReader, Auto и Paper Engine; вход по проверенному
close закрытой свечи, защитные выходы до следующих входов, existing conservative
SL/TP/gap policy. SL/TP fallback происходит только внутри временного paper ledger.
Работающие настройки и Auto на Render не активировались и не менялись.

## Причинность и ускорение

`scripts/replay_aura_csv.py` — отдельный offline адаптер существующих
`import_binance_csv.py` и `backtest_aura_history.py`. Он не заменяет стратегию
и не импортирует Strategy Lab execution. Production функции признаков
используются без изменения формул. Причинные признаки вычисляются один раз;
evaluate получает только срез features/facts до текущей свечи и фактическую
историю до её close. Future prices/outcomes/MTF не доступны текущему решению.
Никакой full-sample normalization/fitting нет.

На реальном dataset прямой production расчёт и cache расчёт полностью совпали
в точках 9999,10000,10500,11500,12879 (индексы selected dataset). Не заявляется
прямой uncached расчёт всех 2880 точек: он был остановлен после 200 свечей
как избыточно медленный. Полный causal-cache прогон завершён.
Unit tests отдельно сравнили весь prefix features и результаты с direct,
изменили будущие цены и доказали неизменность прошлого сигнала.

Полный JSON содержит 2880 решений, журнал сделок, статистику, gate failures,
параметры, data/config/code hashes. Equity curve имеет только baseline point:
production engine не записывает пустые рыночные тики без позиций; flat equity
следует из неизменного ledger, не из придуманных точек.
Monthly attribution в existing backtester использует close/event UTC: в JSON
2879 решений принадлежат сентябрю и одно — границе 1 октября. Это последняя
сентябрьская свеча, не дополнительная октябрьская свеча; всего именно 2880.

## Воспроизведение

Из корня репозитория, с локально установленными requirements:

```bash
python -B scripts/replay_aura_csv.py BTCUSDT-15m-2026-05_to_09.csv \
  --end-date 2026-10-01 --max-seconds 3600 \
  --output /tmp/aura-september-2026-result.json
```

В этой sandbox понадобился `--sandbox-poll`: диагностический timer 10ms для
пробуждения asyncio selector при завершении worker thread. Это явный флаг
standalone script; production event loop не изменялся. Без него прямой запуск
зависал на ожидании thread wakeup. Для медленного полного пересчёта каждого
prefix предусмотрен `--direct`; он не требуется для обычного воспроизведения.
Output должен быть новым файлом. История, CLI и ledger не используют сеть.

Сохранённый полный JSON: `docs/AURA_SEPTEMBER_2026_BACKTEST.json`.
SHA256 JSON:
`c619e6cde836bc3a7a20cfb1bc997c5bebf1ab4a327c54d0d193610179441ca1`.
Исходный CSV не копируется в GitHub; для повторения нужен этот же файл по hash.

## Проверки и ограничения

- Полный Python suite: **721 passed**, одна Starlette deprecation warning.
- Целевые CSV/backtest/cache tests: **39 passed**.
- Все пять JavaScript suites прошли; суммарно **101 tests**.
- Syntax/import, heuristic credential scan, private-client/exchange-write scan: PASS.
- ECC architecture/security/trading-math reviews: cache scope/prefix guards,
  immutable vectors, временный ledger, независимая Decimal PnL cross-check
  существующего replay и past-only outcome purging проверены. Ключи не читались.
- FastAPI0.141.1, uvicorn0.52.1, httpx0.28.1, websockets16.0, NumPy2.3.5;
  exact requirements-pinned environment не переустанавливался.

Это counterfactual production Paper replay на предоставленной истории,
не воспроизведение реальных состояний Render, доставки WS или outages.
Нет новых spread/slippage/funding/liquidity моделей и forced-close на конце.
Данных одной пары/месяца и отсутствия сделок недостаточно для оценки доходности.
Live Render/Android и реальные account requests не проверялись.

Вывод: в данном сентябрьском dataset текущий Historical Pattern не создаёт
подтверждённых торговых сигналов из-за недостаточной аналоговой выборки и
связанных evidence gates. Увеличивать количество сделок изменением порогов
в рамках этого задания нельзя. Следующий безопасный шаг — независимая проверка
этого отчёта и диагностика распределения similarity/числа аналогов, без
самовольной оптимизации или изменения live-настроек.

# Aura Backtest Lab 1.0 — offline replay

Это модель исторического исполнения, не реальные сделки и не проверка production.
Вердикт: **INSUFFICIENT_EVIDENCE**. Прибыльность не подтверждена независимо.

Источник: `BITGET_USDT_FUTURES_BTCUSDT`. Файл данных: `f033ece15f9b510212c8267bcc69cbd9603a90f13187025472ccd9a8e7154481`.
Config: `a652c21ee2148c19ec835db4ae18e96ab36ce789d2d3e55798a2de241ec8c8a4`; code: `474acefc8de51af317ae4e710c3109264ac230fe2be5ea2374c4bef0ff24fdc8`.

| Период / расходы | Сделки L/S | WR % | Net USDT | Return % | PF | Max DD % | Expectancy | B&H full / capped USDT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development-cost1 | 1 (1/0) | 0.00000000 | -19.75228134 | -0.19752281 | 0.00000000 | 0.22461272 | -19.75228134 | 2377.71301197 / 475.84568882 |
| development-cost1.5 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | 2358.30945168 / 472.26349989 |
| development-cost2 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | 2338.92942870 / 468.68145540 |
| validation-cost1 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | -270.75881088 / -54.19460376 |
| validation-cost1.5 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | -286.31195812 / -57.12637644 |
| validation-cost2 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | -301.85280772 / -60.27488712 |
| test_reused-cost1 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | 874.78613635 / 174.95722727 |
| test_reused-cost1.5 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | 857.43171634 / 171.61886748 |
| test_reused-cost2 | 0 (0/0) | undefined | 0 | 0.00000000 | undefined | 0.00000000 | undefined | 839.42777480 / 168.27538210 |

## Периоды и независимость

- development: 2026-07-06T00:00:00Z — 2026-08-27T00:00:00Z exclusive; **NOT_INDEPENDENT**; PREVIOUSLY_VIEWED_CALENDAR, EXPOSURE_REGISTRY_NOT_PROVEN_COMPLETE, CONFIG_FROZEN_AFTER_PERIOD_STARTED, ASSUMED_HISTORICAL_AVAILABILITY.
- validation: 2026-08-27T00:00:00Z — 2026-09-13T08:00:00Z exclusive; **NOT_INDEPENDENT**; PREVIOUSLY_VIEWED_CALENDAR, EXPOSURE_REGISTRY_NOT_PROVEN_COMPLETE, CONFIG_FROZEN_AFTER_PERIOD_STARTED, ASSUMED_HISTORICAL_AVAILABILITY.
- test: 2026-09-13T08:00:00Z — 2026-09-30T16:00:00Z exclusive; **NOT_INDEPENDENT**; PREVIOUSLY_VIEWED_CALENDAR, EXPOSURE_REGISTRY_NOT_PROVEN_COMPLETE, CONFIG_FROZEN_AFTER_PERIOD_STARTED, ASSUMED_HISTORICAL_AVAILABILITY.

## Решения и ограничения

Закрытых 5m решений: 24960; подтверждённых LONG/SHORT: 1.
Причины решений: `{"NO_ENTRY_CONFLUENCE": 2882, "RSI_NOT_CONFIRMED": 2607, "TREND_NOT_CONFIRMED": 15219, "NO_ORDERED_SWING": 907, "CONFLICTING_4H_CONTEXT": 3242, "CLOSED_CANDLE_NOT_CONFIRMED": 64, "INSUFFICIENT_RR_AFTER_COSTS": 38, "TREND_5M_15M_1H|CLOSED_RSI_MOMENTUM|EMA_FIBONACCI_CONFLUENCE|CLOSED_CANDLE_CONFIRMATION|RR_AFTER_COSTS": 1}`.

Сигналы/решения, события, сделки и equity хранятся отдельными CSV. Equity/Drawdown SVG — иллюстрация; метрики считаются по полной минутной кривой и opening marks, не по прореженному графику.

- История и все показатели — исследовательские; независимость test определяется полным календарным реестром, не новой биржей/файлом.
- Историческое время публикации не наблюдалось: close+delay — явное допущение архивного набора.
- OHLC open не гарантирует Bitget fill: следующий доступный минутный open + adverse spread/slippage + tick rounding — модель.
- Нет достоверной полной совместной истории funding + mark prices; funding NOT_INCLUDED. Итог не является PnL после всех возможных расходов.
- Контрактные tick/lot/min-notional приняты фиксированными допущениями; их исторические изменения и ликвидность L2 не доказаны.
- Стопы моделируются по минутному OHLC, SL имеет приоритет при SL+TP; гэп может превысить риск 0.5% и лимит просадки.
- Дневной лимит и drawdown guard наблюдают modeled minute OPEN marks; закрытые marks используются для статистики, не для решения на более раннем open.
- Дневная база equity фиксируется первым минутным open UTC-дня. Guard-выход — следующий доступный open после задержки; круглосуточное исполнение не доказано.
- SEGMENT_END_LIQUIDATION_ESTIMATE — принудительная бухгалтерская оценка конца сегмента, не гарантированный торгуемый close.
- Каждый сегмент начинает с 10000 USDT, позиции не переносятся через границы. B&H full — иной риск/exposure; capped B&H и cash даны отдельно.
- Стресс расходов повторно применяет risk/RR guards к тем же frozen signals; набор исполненных сделок может различаться.
- Нет реальных котировок bid/ask, L2/liquidations, leverage>1, funding или exchange orders. VectorBT не установлен.

Никаких изменений PAPER/Active43/production, БД, scheduler, ключей или ордеров.

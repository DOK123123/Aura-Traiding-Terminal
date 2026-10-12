# Зафиксированный протокол до расчёта

Конфигурация: `FIXED_STRATEGY_PROTOCOL.json`. Она сохранена до первого прогона
этого исследования. Май–июль — development, август–сентябрь — test; конец
1 октября исключён. Первые 500 свечей мая используются только как warm-up:
development performance начинается 6 мая 05:00 UTC. Test начинается 1 августа
с новым ledger; доступны 8832 причинные свечи прошлого. Параметры не обучаются
и не оптимизируются. Август/сентябрь были просмотрены в предыдущих задачах,
поэтому термин «слепой, ранее нетронутый holdout» здесь был бы неверным.

A: Donchian20 breakout по close относительно предыдущих high/low (текущая
свеча исключена), exit по противоположному Donchian10. B: только событие
пересечения EMA20/50, exit по обратному пересечению. A/B: stop/target distance
2%/4% **signal close**, центрированные на следующем actual entry fill;
после gap это не ровно 2%/4% entry. C: Donchian20 плюс close выше/ниже EMA50;
exit по Donchian10 или потере close/EMA50 направления. SL2ATR14, TP4ATR14,
ATR Wilder из данных до signal close. EMA seeded через SMA и причинный
recurrence. Стопы фиксируются на входе, не trailing.

Все A/B/C используют существующий независимый `app.lab.execution.simulate`:
10000 USDT, 10bps fee и 5bps adverse slippage на fill, 1% fee/slippage-inclusive
stop risk, cap2000 USDT, одна позиция, Decimal. LONG/SHORT — виртуальная
экспозиция с 1x collateral; это не реальный Spot short. Решение на close,
entry/strategy exit на next open. Stop-gap хуже stop, target-gap не лучше
target, оба касания → stop. Возможен SL/TP в entry bar после его open.
Сигналы входа при занятой позиции игнорируются; opposite crossover закрывает
позицию next open без немедленного переворота. Сигнал последней свечи сегмента
не переносится в следующий. Liquidation только на конечном close сегмента;
между августом и сентябрём позиции не сбрасываются.

Buy-and-hold: заранее запланированный LONG на first open и exit на final close,
с теми же fee/slippage. Показываются capped2000 и classic10000 allocation.
У passive benchmark нет защитного SL и риск не эквивалентен stop-risk A/B/C.
Production Historical Pattern показывается отдельно в родном Paper replay;
он не ранжируется с общим next-open движком, потому что перенос изменил бы
его исполнение. Неизменённые PatternConfig/reader/Auto/Paper, settings defaults
с явным PAPER_SETTINGS, не проверенные реальные Render settings.

Полные журналы/curves и monthly PnL должны раскрывать распределение cashflows:
entry fees относятся к месяцу entry, gross PnL и exit fee — месяцу exit.
Fee-inclusive trade PnL относится месяцу exit. Эти две monthly метрики могут
отличаться для позиции, пересекающей границу месяца. Monthly drawdown отслеживает
equity от предыдущего close; whole-segment drawdown включает глобальные peaks.

Все файлы research-only, нет сетевых запросов за котировками, аккаунтов/ключей,
UI/API routes, SQLite live-state или activation. Полный 14688-row CSV читается
существующим importer с его защитными лимитами; Lab UI/API лимиты не снимаются.

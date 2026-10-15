# Aura 4.2 — STALE_DATA: диагностика и исправления

15 октября 2026. База main: c42def3a6e6a2793c578c3cdfbf44e0cfcdd3bc0.

## Факты и пределы вывода

Журналы Actions прочитаны без вывода credentials:

- #15, 12:42:24 UTC: NO_NEW_CANDLE, ON, ACTIVATION_BASELINE, processed=False,
  opened=0, closed=0.
- #16, 12:48:41 UTC и #17, 12:49:57 UTC: attempt=1/3 http=NONE code=STALE_DATA.
- Все три события workflow_dispatch. Регулярность schedule этим не доказана.

`http=NONE` здесь не доказывает отсутствие HTTP-ответа: scheduler также печатает
NONE при отказе verified_result на HTTP 200 с PAUSED. Runtime-логов Render и
авторизованного доступа к текущей БД у агента нет.

Точная первичная причина #16/#17 **не установлена**. Старые журналы не содержат
времени последней свечи, исходного статуса MarketContext или стадии сбоя.
Подтверждён дефект классификации: strategy() для любого status != OK, включая
UPSTREAM_TIMEOUT, ANALYSIS_TIMEOUT, NETWORK_ERROR и INVALID_CLOSE_TIME, выдаёт
STALE_DATA. Это скрывает первичную ошибку, но не разрешает небезопасный вход.

Публичная проверка (без ключей и ордеров): Binance Spot
`https://data-api.binance.vision/api/v3/klines`, BTCUSDT, interval=15m,
limit=2, endTime=expected_closed_at*1000-1: HTTP 200.
checked_at=1792069002; expected_closed_at=1792068300;
last_open_ms=1792067400000; last_close_ms=1792068299999; две строки.
Миллисекунды open/close корректны; exclusive close = open/1000 + 900.
Это проверка доступности из исследовательской среды в момент проверки,
не доказательство работоспособности Binance из Render во время #16/#17.

## Подтверждённые дефекты и минимальные исправления

1. **Средняя severity: потеря причины ошибки.** Service.snapshot теперь до вызова
   стратегии переносит только whitelisted ошибки MarketContext в отказ Auto42.
   Настоящее устаревание остаётся STALE_DATA. Scheduler сохраняет эти коды в логах.
   Формулы и условия стратегии не изменены.
2. **Средняя severity: TTL игнорирует закрытие новой свечи.** MarketContext может
   вернуть предыдущий успешный snapshot в пределах 30 секунд после его получения,
   даже если наступила новая граница 15m. Безопасность блокирует вход, но запрос
   свежих данных не выполняется немедленно. Новый отдельный адаптер
   app/automated/market_data.py делает один boundary refresh для Auto42,
   используя тот же singleton task. Cooldown сохраняется; повторные ошибки
   подчиняются прежнему TTL. Нет бесконечного retry и дублирующих загрузок.
   Этот дефект воспроизведён fixture-тестом, но НЕ объявляется доказанной причиной
   запусков через несколько минут после 12:45 UTC.
3. Добавлена безопасная диагностика в owner status, backend logs и ERROR events:
   last_closed_at, expected_closed_at, fetched_at, analyzed_at, checked_at,
   cache_requested_close, cache_state, market_status, error_source, фиксированный
   источник Binance. Неизвестные времена — null, без фиктивных отметок получения.
   ERROR event сохраняется в существующем журнале и доступен после restart.
   Текущая in-memory диагностика после restart неизвестна до нового запроса;
   старое доказательство нужно читать в журнале, не выдавать за новый запрос.
4. После задержки БД свежесть проверяется повторно как раньше; при пересечении
   границы диагностика явно помечает POST_STORAGE_FRESHNESS и новый expected time.

## Восстановление и безопасность

Сохраняется data_recovery_armed только для ранее включённого владельцем режима,
при допустимой временной ошибке и отсутствии risk block. Timeout/сеть/STALE и
временные RATE_LIMIT/UPSTREAM_HTTP_ERROR/PUBLIC_DATA_UNAVAILABLE допускают следующую
проверку. Новый tick получает свежий snapshot; только успешная проверка позволяет
восстановить прежний ON. STOP/EMERGENCY, hard gap и risk pause не включаются сами.

При ошибке очищается pending, watermark не продвигается. Результат/ошибка tick
атомарно записываются; повтор в том же 5-минутном слоте не повторяет вход.
После restart повторное чтение восстановит состояние из БД; неуспешная диагностика
не подменяет портфель. Никаких прямых операций Supabase или START агент не выполнял.

Данные по-прежнему загружаются фиксированным public Binance Spot GET, не более
5 страниц, ≤4175 свечей, инкрементально с проверкой overlap. Незакрытые свечи,
неправильный close_time, дубликаты и нарушения OHLCV не допускаются. Реального
источника ошибок Render (DNS/TLS/HTTP/CPU timeout) старые записи не доказывают.

## Совместимость и review

Первоначальный вариант менял MarketContext и провалил тест совместимости
shipped analog artifact: 1111 passed / 1 failed. Причина — source fingerprint
этого versioned модуля. Изменение полностью отменено; отдельный адаптер Auto42
не меняет исходник MarketContext, признаки, аналоги и существующий replay.
Пакет не пересоздан и его проверка не ослаблена.

Отдельные code/security/reliability review passes: task reuse, bounded retry,
recovery flags, whitelist diagnostics, closed-candle gates, immutable artifacts.
Стратегия, engine, риск, SL/TP, UI, workflow и авторизация неизменны.
Синтетические fixtures используются только для регрессий, не оценки доходности.

## Проверка на Render владельцем

После деплоя нового main проверить owner /api/auto42/status и журнал:
`diagnostics.market` и ERROR.payload.market. Значения timestamp — UTC seconds.
Сопоставить expected_closed_at=floor(checked_at/900)*900 и last_closed_at;
fetched_at — фактическое завершение получения истории, analyzed_at — время анализа.
При ошибке загрузки fetched_at может отсутствовать: это не успешное получение.

Ожидать следующий scheduler tick без RESET и без повторного START. Ранее ON,
временно PAUSED/armed должен восстановиться только с валидными свежими данными.
Проверить отсутствие повторного входа и продвижение watermark только после
обработки новой закрытой свечи. Если отказ остаётся, зафиксировать безопасные поля
и исходный код: UPSTREAM_TIMEOUT, ANALYSIS_TIMEOUT, INVALID_CLOSE_TIME и т.д.
Не сообщать о решённой production-проблеме, пока новая диагностика и успешный tick
не подтверждены. Если PAUSED не armed или есть hard gap/risk block — автоматическое
снятие такого запрета не предполагается.

Команды: полный `python -m pytest -q`; все `node tests/*.cjs` по отдельности;
AST app/scripts/tests; import app.main; загрузка штатного AnalogIndex.
Тестовая Cloud среда использует PYTHONPATH=/workspace/ecc-audit-deps:$PWD,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, python -B, enable_sandbox_poll() и
pytest.main(['-q','-p','no:cacheprovider','--tb=short']). Production loop неизменён.

## Итог проверок

- Полный Python suite: **1114 passed**, 0 failed, 1 Starlette/AnyIO deprecation warning, 80.67 s.
- Все 10 JS suites: **155 passed**, 0 failed.
- AST, import app.main, совместимость shipped analog artifact: PASS.
- Новые 6 тестов: исходные коды отказов, строгая блокировка STALE, граница нового
  close, bounded retry/cooldown, durable error/restart/dedup, scheduler code whitelist.
- Реальный авторизованный Render tick, production recovery и Android: NOT RUN.
- Не выполнялись реальные сделки, private exchange calls, изменение конфигурации
  Render или данных Supabase. Deploy нужен владельцу; автоматический Render deploy
  может самостоятельно сработать на push. Успех production пока не подтверждён.

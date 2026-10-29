# Отдельные review-проходы перед коммитом

## Архитектура и code review

Проверены пути public REST/WS → ограниченные окна → чистый расчёт → DOM →
явное копирование → owner/CSRF POST → серверная котировка → network-free commands
→ transaction/CAS → persistent receipt/state. Обратного вызова OPEN из аналитики
нет. Исходные closed Analyst формулы и Active43 не меняются.

Исправленные подтверждённые дефекты/несовместимости:

- Реальный Bitget WS snapshot содержит 500 строк: initial cap 300 делал perpetual
  reconnect. Bounded 1000 rows / 1 MiB и регрессия на 500, сохранение 201.
- Closed-feed watcher старого главного графика мог перезаписывать новый LIVE-статус.
  Он сохраняется для legacy страницы, пропускается только на manual-live странице.
- В #57 исполнение bid/ask не добавляло adverse slippage. В Manual Paper Service
  добавлены 5 bps, в stop-risk и marks/realized PnL тоже; core reference tests обновлены
  на независимо рассчитанные суммы, а прямой legacy commands contract сохранён.
- Дневного риска 2% в #57 не было: добавлена реконструкция baseline из journal.
- При конкурентном cold-start SQLite PRAGMA WAL мог вернуть database is locked.
  Процессный mutex сериализует настройку WAL; сами операции и процессы защищены
  SQL BEGIN IMMEDIATE. Дубли не скрываются как новый результат.
- Старые UI controls глубины не отражали 201-свечный LIVE-буфер: disabled с честной
  подписью; переключение пяти таймфреймов остаётся доступным.
- Защитный статус LIVE больше не сохраняется в cold-start grace после уже
  установленного LIVE и потери свежести quote; watchdog отключает соединение.

## Security review

Owner auth на state/quote/order/close; CSRF header/same-site/origin; строгая схема
без клиентских execution price; no-store/nosniff; sanitize error codes; только
официальный public host и fixed GET, redirects запрещены. Нет Bitget API keys,
приватного exchange client, real order endpoint, reset/topup или Active43 authority.
Серверные Supabase ключи не проходят в браузер. SQL RLS запрещает anon/authenticated,
RPC SECURITY INVOKER и service_role only; применено только в disposable local PG.

Отдельные namespaces SQLite/Supabase/localStorage, неизвестные outcomes сохраняют
тот же ID. Изменение сигнала/копирование плана никогда не POST. Внешний трафик всех
автоматических regression тестов mocked или network-isolated; production вызовов
и изменений не было. Live public network probe был отдельным чтением только Bitget.

Неразрешённых critical/high review findings после исправлений не обнаружено.
Это внутренние отдельные review-проходы по checklist репозитория, не внешний аудит.
Риски модели, отсутствие 24/7 и физического Android явно перечислены в отчёте.

## Дополнение: два профиля и WAIT audit

Проверены отдельным проходом `legacyAnalyze → analyzeProfiles → conditional plans
→ profile selector → manual-copy`. Консервативный LONG/SHORT/WAIT совпал с
legacy на 124800 реальных минутных срезах. Допуск entry zone теперь совпадает
с уже существующим ценовым gate; это исправление контракта уровней, не добавление
сигналов. Умеренный не обходит свежесть, обязательные подтверждения, R/R или
серверные риски. Против 4h нужны дополнительные сила 1h и netRR 2.

Ни profile change, ни условный WAIT-план не вызывают POST. Общая причина WAIT
отделена от всех невыполненных условий и warning. На плохих данных potentials
очищаются. Сохраняется выбранное пользователем раскрытие LONG/SHORT на каждом
LIVE обновлении; count подтверждений явно не вероятность. Источник, цены,
API/БД, actual Manual Paper и Active43 не изменяются.

Offline model проверен LONG/SHORT независимыми известными числами, SL-first,
отложенным входом, duplicate key и отсутствием использования будущего close
для освобождения позиции. Протокол/код хешируются и контролируются в конце
прогона. Нового OOS нет, выборки сделок нет, поэтому нет вывода о прибыльности
и нет post-results настройки параметров. Physical Android остаётся NOT TESTED.
Неразрешённых critical/high findings в этом проходе не выявлено.

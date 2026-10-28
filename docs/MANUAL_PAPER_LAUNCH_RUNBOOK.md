# Бесплатный запуск Manual Paper v1

Целевой вариант: **Render Free + существующий Supabase Free**, стоимость базовых сервисов 0 USD/месяц в пределах бесплатных лимитов. Платный диск и переход Render на Starter не нужны. Это новая рекомендуемая инструкция вместо первоначального SQLite/deploy плана.

Код находится в PR #57 и не развёрнут. В рамках разработки production, Active43 и рабочая схема Supabase не меняются. Применение SQL и production deploy — отдельный согласованный шаг.

## Что уже проверено

- Render: `Aura-Traiding-Terminal`, `srv-db5tonlckfvc73be2m5g`, Free, Virginia, один экземпляр, ветка main, Auto-Deploy Off. Live commit при проверке: `b721a0c`.
- Build: `pip install -r requirements.txt`; start: `python start_web.py`, один worker.
- Health 200; owner endpoint требует входа (401); публичный API вернул 500 свежих Bitget 1m Futures candles (`stale=false`).
- Supabase: существующая Aura (`uvcbhicbnqpqobxnufph`), ACTIVE_HEALTHY, PostgreSQL 17; размер базы по read-only SQL 17,42 MB. Таблиц `aura_manual_paper_v1_*` нет.
- Никакие секреты не получены из Render в тестовую среду. Dashboard/env требуют отдельного входа; текущие Manual Paper переменные не прочитаны.

Результаты относятся к проверке 26.10.2026. Перед выпуском повторно сверить актуальные live SHA, owner state и usage.

## До применения изменений

1. Проверить зелёный **CI именно последнего SHA PR #57**, включая новый настоящий PostgreSQL test. Старые результаты на другом commit недостаточны.
2. Убедиться в доступной бесплатной квоте Supabase/Render и включённых ограничениях расходов. Лимиты общие с остальными функциями Aura. Не включать платные add-ons.
3. Прочитать owner status Active43 и позиции без изменений. Если есть активная автоматическая торговля, позиция или неизвестный исход, согласовать окно restart отдельно; самостоятельно переключать Active43 нельзя. Ранее в его логах были `HISTORY_CANDLE_CHANGED`/`RATE_LIMIT`; эти проблемы не исправляются новым Manual Paper backend.
4. Получить отдельное согласие на применение **только выделенной Manual Paper SQL-схемы** и на deploy. Ни merge, ни deploy не выполняются автоматически.

## Схема Supabase

В SQL Editor проекта Aura после отдельного согласования выполнить целиком [scripts/manual_paper_schema.sql](../scripts/manual_paper_schema.sql).

Скрипт создаёт только 2 Manual Paper таблицы, 3 RPC и append-only trigger function. Он не создаёт/меняет Active43/Auto42/Practice, не открывает позиции и не создаёт начальный баланс. Повторное применение не сбрасывает существующие данные. RLS включён, browser roles закрыты. Server-only service_role получает доступ к выделенным объектам.

После применения проверить через metadata/адвайзеры RLS и отсутствие EXECUTE для `anon`/`authenticated`, затем read-only RPC `aura_manual_paper_v1_load(NULL)`. Для нового счёта он возвращает null; это нормально и не создаёт account. Не выдавать браузеру `service_role`/secret key. Не отключать RLS для исправления ошибок.

SQL-интеграция тестируется в CI на отдельном локальном Docker PostgreSQL без сетевого доступа и без production-ключей; это не заменяет проверку реально применённой схемы/прав в Supabase после разрешения.

## Render — без смены тарифа и диска

Оставить **Free, один экземпляр, Auto-Deploy Off**, существующий build/start. Не добавлять persistent disk, PostgreSQL, Key Value или worker в Render.

В Environment добавить только:

```text
AURA_MANUAL_PAPER_ENABLED=true
AURA_MANUAL_PAPER_STORAGE=supabase
AURA_MANUAL_PAPER_SUPABASE_URL=https://uvcbhicbnqpqobxnufph.supabase.co
AURA_MANUAL_PAPER_SUPABASE_SERVICE_KEY=<server-only service_role JWT or secret key>
```

`AURA_TESTNET_VIEW_PASSWORD` — существующий owner-пароль ≥12 символов. Значения Active43 и его scheduler не менять. Для нового режима `AURA_MANUAL_PAPER_DB`/`MOUNT` не используются. Не заменять всю коллекцию env; сохранять остальные ключи. Секрет вводить только в Render, не в чат/код/скриншот.

До согласованного deploy выбрать **Save only**. Не нажимать Save and deploy случайно. Сохранение env ещё не меняет работающую версию.

После явного разрешения развернуть конкретный проверенный SHA из PR через Deploy a specific commit либо согласованный процесс слияния/выпуска. Не нажимать Deploy latest commit, пока main не содержит эту версию. Дождаться **Live** и сверить SHA. Это перезапуск всего приложения; предыдущий пункт о состоянии Active43 обязателен.

## Проверка без production-сделок

1. `GET /api/health` должен вернуть 200.
2. Открыть терминал, войти владельцем через `/api/paper/login`: имя `aura`, существующий пароль. Открыть **Manual Paper**, не Active43.
3. У нового счёта: баланс 10000 USDT, реализованный PnL 0, позиция отсутствует, журнал пуст; хранение **Supabase · баланс сохранён**.
4. Убедиться, что свежий bid/ask ≤5 секунд, ошибок рынка/БД нет. Никакие LONG/SHORT/Close/PAPER/START не нажимать.
5. Обновить страницу/закрыть Chrome и открыть снова: счёт тот же. После отдельно согласованного server restart сравнить баланс/версию/позицию/историю: ничего не сброшено.
6. При недоступности Supabase должны появляться ошибки и блокироваться операции; новая SQLite/временная база не создаётся. Не удалять таблицы для исправления проблем.

Дополнительная read-only команда существует в коде:

```bash
python -m scripts.manual_paper_preflight
```

На Render Free Shell/SSH не поддерживаются: **не покупать тариф только для этой команды**. Достаточно защищённых GET панели; команду можно запустить позже в согласованной серверной среде. Она не создаёт счёт, проверяет существующий журнал/конфигурацию и публичный ticker; секреты не выводятся. При новом пустом счёте допускается `READY_EMPTY_DATABASE_NOT_INITIALIZED`. Установленные env локальной копии не подтверждают env production.

## Проверка с телефона

1. В Android Chrome открыть `https://aura-traiding-terminal.onrender.com/`. Первый запуск после сна Free может занять около минуты.
2. Открыть Manual Paper, войти владельцем. Биржевые ключи не вводить.
3. Проверить читаемость баланса/полей/журнала вертикально и горизонтально, источник Supabase и timestamps котировки.
4. После reload и закрытия/повторного открытия Chrome баланс должен сохраняться. Если видна старая панель, обновить страницу и проверить SHA deploy.
5. Отключить интернет телефона: после истечения свежести котировки кнопки операций должны блокироваться, текущие equity/PnL скрываться. После возврата сети нажать «Обновить».
6. Пробные сделки в production не выполнять без отдельного разрешения. LONG/SHORT, loss/fees, SL/TP, повтор после потери ответа и restart проверяются в изолированных тестах.

## Ограничения бесплатного режима

- Render Free спит после 15 минут без входящих запросов; при сне/сбоях сервера, Bitget или Supabase SL/TP не проверяются. Промежуточные касания не восстанавливаются. Работа 24/7 и выход точно на уровне SL не гарантируются.
- Supabase хранит счёт независимо от временного диска Render. Free может приостановить проект после недели неактивности; автоматические backup не включены. Нужны отдельные согласованные резервные копии.
- Не добавлено принудительное удержание Render от сна, фоновый keep-alive или дополнительный scheduler. Обычные запросы вкладки идут только при использовании.
- 500 MB базы и 5 GB egress Supabase Free — общие лимиты; объём/доступность квот до выпуска проверить. Snapshot счёта ограничен 1 MiB; на новые входы оставляется резерв для закрытия, receipts не удаляются. Расширение/архивирование — отдельная задача.
- Это учебная виртуальная торговля, не источник доказанной доходности. Funding и полная глубина стакана не моделируются.

Источники: [Supabase Pricing](https://supabase.com/pricing), [Render Free](https://render.com/docs/free), [Render deploys](https://render.com/docs/deploys), [Render Environment](https://render.com/docs/configure-environment-variables), проверено 26.10.2026.

# Paper Practice — PostgreSQL verification и запуск владельцем

Работать только с Draft PR #12. Эта инструкция не является разрешением на merge
или deploy. В ходе разработки рабочая Supabase не открывалась, production
настройки не менялись, реальные ордера не отправлялись.

## Что проверено локально

Результаты настоящего PostgreSQL, точная версия, digest Docker-образа, SHA256
миграции и отдельные сценарии находятся в
`PAPER_PRACTICE_POSTGRESQL_VERIFICATION.json`. Это PostgreSQL 16 в контейнере
без сети и опубликованных портов, с отдельной временной базой. SQLite или mock
базы в этой проверке нет. Проверены существующие Service, проверка ответов Store,
Paper Engine и реальные SQL RPC. Сетевой HTTP-адаптер заменён локальным вызовом
psql; Supabase PostgREST/JWT gateway и Render этим **не проверены**.

Цены 100/101 и другие значения в отчёте — исключительно воспроизводимые
локальные фикстуры BTCUSDT. Их нельзя переносить в production. Результаты
тестовых сделок не являются результатами стратегии или LIVE VERIFIED.

Исправлена условная ошибка прав: широкие default grants могли оставлять
`anon`/`authenticated` доступ к sequence, а `service_role` — прямой доступ к
таблицам. Миграция теперь явно отзывает эти права только у новых
`aura_practice_*` объектов. Три SECURITY DEFINER RPC доступны service_role;
прямое изменение ledger через API-роли запрещено. RLS проверена отдельно от
GRANT/REVOKE, временным предоставлением прав внутри тестовой базы.

Повторить локально бесплатно при наличии Docker:

```bash
python -m scripts.verify_practice_postgres --output /tmp/practice-pg-result.json
```

Нужны зависимости проекта и доступ к локальному Docker socket. При отсутствии
образа Docker скачает официальный образ с зафиксированным digest. Runner
ограничивает контейнер 512 MiB RAM / 1 CPU, не принимает DSN/URL/ключ Supabase,
создаёт отдельную базу и удаляет свой контейнер и volume после завершения.
Запускать локально, не на Render. Ошибка прекращает проверку; TRUE выдаётся
только после прохождения всех проверок. Обычный pytest пропускает Docker-тест,
если нет явного `AURA_PRACTICE_VERIFY_POSTGRES=true`; пропуск не является PASS.

## 1. Supabase Free — использовать существующий проект

Отдельная платная база, worker и платный API для этой функции не нужны.
Можно использовать текущий проект Supabase Aura 4.2: новый счёт и журнал будут
в `public.aura_practice_account` / `public.aura_practice_events`. Старые торговые
таблицы, балансы и позиции миграция не изменяет. Не запускайте заново
`auto42_schema.sql` и не сбрасывайте счета.

Раздельные таблицы обеспечивают изоляцию обращений приложения, но общий
service-role ключ обладает широкими правами проекта. Он хранится только на
сервере. Общая база также означает общие квоты: исчерпание места/трафика/ресурсов
может повлиять на Aura 4.2. Перед включением проверьте актуальные ограничения
своего тарифа и свободное место в Dashboard → Usage. Не подключайте upgrade.

При открытой позиции монитор проверяет цену примерно каждые 3 секунды; это до
28 800 UPDATE в сутки, если каждый раз приходит новая сделка. Запись содержит
подробности позиции, поэтому долгий непрерывный тест расходует место. Даже без
позиции включённый монитор читает состояние каждые 3 секунды. На первом этапе
выполните короткий OPEN → UPDATE → CLOSE и затем отключите Practice. Журнал не
очищается автоматически. Не удаляйте историю Aura 4.2 ради освобождения места.

Render с засыпающим web service не гарантирует защитные проверки во время сна.
SL/TP виртуальные, по следующей наблюдённой свежей цене, а не биржевые заявки.
Касание между опросами/во время сбоя может быть пропущено. Дополнительный платный
ресурс не создаётся; если нужна круглосуточная доступность, это отдельное решение
владельца. Длительная работоспособность на текущих квотах не подтверждена.

## 2. Безопасно применить SQL — вручную после review

1. Убедитесь, что открыт правильный существующий Supabase проект. Сохраните
   доступную резервную копию/собственный защищённый локальный backup; не
   публикуйте дамп и ключи в Git. Наличие автоматических backups на Free не
   предполагается. Не изменяйте настройки Aura 4.2.
2. В SQL Editor выполните только чтение предпосылок:

```sql
select current_user, current_database();
select rolname from pg_roles
where rolname in ('anon','authenticated','service_role');
select extname, extnamespace::regnamespace as schema
from pg_extension where extname='pgcrypto';
select to_regclass('public.aura_auto42_account') as existing_auto42,
       to_regclass('public.aura_practice_account') as practice_account,
       to_regclass('public.aura_practice_events') as practice_events;
select pg_size_pretty(pg_database_size(current_database())) as database_size;
```

   Должны существовать API-роли и схема `extensions`; pgcrypto должна быть
   доступна в `extensions`. Если расширение уже установлено в другой схеме,
   **не переносите его и не удаляйте**: это может затронуть Aura 4.2. Остановитесь
   и разберите несовместимость отдельно. Локальная проверка использовала
   Supabase-подобные роли/схему, но не конфигурацию вашего проекта.
3. Возьмите **весь** `scripts/practice_schema.sql` именно из проверенного коммита
   PR #12, сверьте SHA256 с отчётом. Просмотрите файл: только practice-объекты,
   отсутствуют DELETE/TRUNCATE/UPDATE существующих счетов.
4. Вставьте целиком в SQL Editor и выполните как владелец БД. В файле уже есть
   `BEGIN`/`COMMIT`: не разбивайте его на отдельные фрагменты. При любой ошибке
   не продолжайте; выполните `ROLLBACK;` в том же сеансе, если он остался в
   транзакции, и сохраните только безопасный код ошибки. Не обходите проверку
   прав выдачей GRANT ALL. SQL не создаёт тренировочный баланс до первого RPC.
5. Повторный запуск этой миграции допустим и проверен с открытой тренировочной
   позицией: существующее состояние не сбрасывается. Не удаляйте таблицы ради
   повторного запуска. `NOTIFY pgrst, 'reload schema'` уже включён в файл.
6. Проверьте новые объекты и права чтением:

```sql
select tablename, rowsecurity from pg_tables
where schemaname='public' and tablename like 'aura_practice_%';
select p.proname, p.prosecdef as security_definer, p.proconfig
from pg_proc p where p.pronamespace='public'::regnamespace
and p.proname in ('aura_practice_load','aura_practice_commit','aura_practice_history');
select role_name,
 has_function_privilege(role_name,'public.aura_practice_load(jsonb)','EXECUTE') as can_load,
 has_function_privilege(role_name,'public.aura_practice_commit(bigint,jsonb,jsonb,text)','EXECUTE') as can_commit,
 has_function_privilege(role_name,'public.aura_practice_history(text,bigint,integer,text)','EXECUTE') as can_history,
 has_table_privilege(role_name,'public.aura_practice_account','SELECT') as direct_account_read,
 has_table_privilege(role_name,'public.aura_practice_account','UPDATE') as direct_account_write,
 has_sequence_privilege(role_name,'public.aura_practice_events_seq_seq','USAGE') as sequence_usage
from (values ('anon'),('authenticated'),('service_role')) r(role_name);
```

   Ожидается RLS=true у двух таблиц, security_definer=true у трёх RPC.
   Только service_role имеет три EXECUTE=true. Прямые права из запроса и USAGE
   sequence должны быть false у всех трёх ролей. Сохраните результаты приватно.
   Если отличаются, не включайте Practice. Настройки trading API менять не нужно.

## 3. Render — подготовить, но не менять без разрешения на deploy

После отдельного разрешения владельца на merge/deploy сначала отключите
нежелательный автоматический rollout, выберите проверенный коммит PR #12 и
оставьте существующий entry point `python start_web.py` с одним worker.
Не включайте Research Lab и не меняйте scheduler.

Добавьте выделенные переменные (значения ключей здесь не приводятся):

```text
AURA_PRACTICE_ENABLED=false
AURA_PRACTICE_SUPABASE_URL=<URL существующего Supabase проекта>
AURA_PRACTICE_SUPABASE_SERVICE_KEY=<серверный service_role ключ этого проекта>
```

Используйте существующий `AURA_TESTNET_VIEW_PASSWORD` длиной не меньше 12 символов;
не заменяйте его ради Practice. Не меняйте `AURA_AUTO42_*` или биржевые переменные.
URL/ключ Practice задаются явно — скрытого fallback к Auto42 нет. Не используйте
anon/publishable ключ вместо service_role. Не копируйте ключ в браузер, логи,
скриншоты, PR или файл репозитория. Устаревший/несовместимый формат ключа должен
давать отказ, а не основание отключать проверки; hosted gateway ещё не проверен.

Любое сохранение Render env может перезапустить приложение: делайте это только
после разрешения. После rollout с Practice=false проверьте `/api/health`,
существующий Auto42 monitor, scheduler tick и сохранённые позиции.

## 4. Включить Practice и проверить реальную связь

После успешных проверок установите `AURA_PRACTICE_ENABLED=true` и выполните
разрешённый restart. Откройте `/api/practice/login`, войдите владельцем:
username `aura`, существующий пароль. Нажмите Connect.

Проверьте `/api/practice/state`: scope=PAPER_PRACTICE_V1,
backend=SUPABASE_PRACTICE_ONLY, валидная revision и время сохранения. На первом
запуске отдельный баланс 10 000 USDT; при повторном — прежний тренировочный
баланс, без переинициализации. `/api/practice/quote` должна вернуть настоящий
свежий BTCUSDT Binance Spot trade. Нет свежей цены/ответа БД — не открывайте.

Если RPC не видна, проверьте применение именно трёх функций и schema reload.
401/403/503 требуют проверки owner/server-key/прав/схемы; не выдавайте anon
доступ и не отключайте авторизацию. Не нажимайте START/RESET Aura 4.2.

## 5. Первая тренировочная LONG

1. Убедитесь, что основной баланс/позиции Aura 4.2 не изменены, Practice явно
   помечена PAPER, нет открытой тренировочной позиции, котировка свежая.
2. Введите SL ниже текущей цены и TP выше неё. Для первого теста можно выбрать
   расстояния около 1% вниз и 2% вверх от текущей цены; обязательно пересчитайте
   уровни по свежей цене. Это ручные параметры только тренировочного счёта.
   Слишком близкие уровни после комиссий/проскальзывания будут отклонены.
3. Нажмите OPEN LONG один раз. Размер рассчитает существующий движок:
   максимум 0.5% риска и 2 000 USDT notional, одна позиция. Нельзя отправлять
   фиктивный сигнал или подставлять локальные тестовые цены.
4. Убедитесь в confirmed receipt, OPEN, ID позиции, Entry/SL/TP на графике,
   размере и комиссии. Дождитесь хотя бы одного UPDATE и актуального PnL.
   Unknown/unconfirmed — это **не подтверждённая сделка**: используйте повтор
   того же сохранённого запроса/UUID, не создавайте второй OPEN.

## 6. Закрыть и проверить Supabase

Нажмите CLOSE POSITION. При неопределённом ответе повторите тот же UUID.
Должны появиться CLOSE того же ID, итоговые комиссии/PnL и пустая позиция.
При реальном достижении SL/TP возможен автоматический CLOSE раньше нажатия;
не создавайте новый OPEN для исправления старого ответа.

В Supabase SQL Editor проверьте только Practice:

```sql
select revision,saved_at,
 payload::jsonb->>'practice_scope' as scope,
 payload::jsonb->>'balance' as balance,
 payload::jsonb->>'fees' as fees,
 payload::jsonb->>'realized_pnl' as realized_pnl,
 payload::jsonb->'position' as position,
 sha256=encode(extensions.digest(convert_to(payload,'UTF8'),'sha256'),'hex') as checksum_ok
from public.aura_practice_account where id=1;

-- Замените только ID на ID из своего receipt; ключи здесь не нужны.
select seq,id,kind,created_at,ingested_at,
 payload::jsonb->>'command_id' as command_id,
 payload::jsonb->'payload' as trade,
 sha256=encode(extensions.digest(convert_to(payload,'UTF8'),'sha256'),'hex') as checksum_ok
from public.aura_practice_events
where kind in ('OPEN','CLOSE')
 and payload::jsonb->'payload'->>'id'='PRACTICE_POSITION_ID_FROM_RECEIPT'
order by seq;
```

Ожидается ровно один OPEN и один CLOSE с одинаковым position ID и checksum=true.
В CLOSE проверьте entry_fee/exit_fee/fees/realized_pnl; баланс после первой
закрытой позиции равен 10000 + realized_pnl. Для UPDATE смотрите последние
события и вложенное `payload.position.id`; ограниченная страница UI не является
полным журналом. Повтор завершённого UUID не должен менять число OPEN/CLOSE и
комиссии. После разрешённого restart проверьте тот же баланс/историю; отдельно
проверьте сохранение открытой позиции и мониторинг при закрытом браузере.

Лишь после этого можно зафиксировать реальный Render/Supabase Practice цикл.
Он **не доказывает автономную торговлю стратегии Aura 4.2**.

## 7. Ошибка и безопасное отключение

1. Прекратите новые OPEN. Не нажимайте RESET, не редактируйте баланс и не
   удаляйте записи. Сохраните приватно UTC-время, receipt/UUID, ID позиции и
   безопасный код ошибки. Повторите неопределённую команду с прежним UUID.
2. Если свежая цена/БД доступны, сначала закройте тренировочную позицию обычной
   кнопкой и проверьте CLOSE в SQL. Затем установите
   `AURA_PRACTICE_ENABLED=false` с разрешённым restart. История останется в БД.
3. Если позиция не может закрыться из-за недоступной цены/БД, отключение флага
   остановит и защитный монитор. Это **не CLOSE**. Зафиксируйте открытое
   состояние, сохраните таблицы и разберите сбой. После восстановления включите
   Practice контролируемо и проверьте восстановление/закрытие; убыток при разрыве
   цены не ограничен гарантированно заданным SL.
4. Ошибку общих квот решайте без удаления Aura 4.2 данных и без отключения её
   scheduler. Автоматический платный upgrade или новый ресурс не требуется для
   отката: отключённая Practice не создаёт монитор/RPC-клиент.

## Статусы

POSTGRESQL_VERIFIED / RLS_VERIFIED / OPEN_CLOSE_VERIFIED относятся только к
настоящему локальному PostgreSQL и указанному в отчёте SQL-адаптеру.
PRODUCTION_READY остаётся FALSE, пока не проверены hosted PostgREST, фактическая
конфигурация и настоящий Render OPEN → UPDATE → CLOSE → Supabase. Никакого
production deploy или доступа к рабочей базе в этой задаче не выполнялось.

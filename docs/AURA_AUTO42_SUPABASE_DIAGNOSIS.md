# Aura 4.2 — диагностика Supabase, 15 октября 2026

Статус: **NOT OPERATIONAL / подключение производственной БД не подтверждено**.
База аудита: `5f495219537222b139141229088b8f4ee368867d`, актуальный main перед изменениями.

## Что установлено

- Указанный владельцем hostname `uvcbhicbnqpqobxnufph.supabase.co` разрешается
  локальным resolver и двумя независимыми публичными DNS-over-HTTPS: Google и
  Cloudflare. Оба вернули Status=0, A=172.64.149.246 и 104.18.38.10.
- Без ключей HTTPS GET к `https://uvcbhicbnqpqobxnufph.supabase.co/rest/v1/`
  вернул **401**. Это подтверждает доступность DNS/TLS/REST из исследовательской
  среды, но не правильность ключа, таблиц, RPC или доступность из Render.
- `https://aura-traiding-terminal.onrender.com/api/health` вернул **200**.
- Сообщение STORAGE_DNS формируется при обнаружении `socket.gaierror` в цепочке
  исключения httpx. Оно не свидетельствует об ошибке пароля, SQL или Data API.
  Точный hostname процесса Render до этого исправления не показывался.
- **Причина конкретного сбоя Render остаётся не установленной**: нет доступа к
  Environment/логам/авторизованному статусу Render. Возможны старая переменная
  в работающем процессе, другой Project URL или временный DNS-сбой Render.
  Эти варианты являются гипотезами, а не диагнозом.

## Архитектура и настройки

`app/main.py` → `app/automated/service.py:configured` →
`app/automated/storage.py:SupabaseStore` → общий валидируемый HTTP transport
`app/forward/storage.py:SupabaseStore`. Прямого PostgreSQL TCP/Database URL,
IPv6 database host и SQL-драйвера в этом пути нет: HTTPS PostgREST RPC.

Используются только:

- `AURA_AUTO42_SUPABASE_URL`: Project URL строго `https://<project-ref>.supabase.co`,
  без завершающего slash, `/rest/v1`, query, пробелов, кавычек, markdown или DSN.
- `AURA_AUTO42_SUPABASE_SERVICE_KEY`: серверный service_role key того же проекта.
- `AURA_AUTO42_SCHEDULER_SECRET`: отдельный scheduler token.
- `AURA_TESTNET_VIEW_PASSWORD`: отдельный пароль владельца.

`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SERVICE_KEY` НЕ являются
алиасами настроек Aura 4.2. Их наличие теперь видно по именам в защищённом JSON
`diagnostics.configuration.ignored_generic_variables`. Значения не возвращаются.
Не делается автоматический fallback на другой проект/ключ/локальную SQLite.
На Render переменная `AURA_AUTO42_SQLITE_PATH` должна отсутствовать.
Клиент создаётся при старте процесса: изменение Environment требует перезапуска.

URL собирается ровно один раз:
`<Project URL>/rest/v1/rpc/aura_auto42_load`, `aura_auto42_commit`,
`aura_auto42_history`. Headers apikey и Authorization остаются серверными.
RPC load может инициализировать первый отдельный портфель; диагностика не
вызывает новый публичный endpoint или скрытый SQL. В ходе этого аудита ни один
авторизованный RPC/tick/control не отправлен.

## Изменения

- Owner-only существующий `/api/auto42/status` возвращает hostname именно
  созданного transport, а не предполагаемую текущую env-настройку. Выводится
  только hostname, прошедший строгий allowlist; никаких сырых URL/headers.
- Категории DNS_ERROR, NETWORK_ERROR, AUTH_ERROR, DATABASE_ERROR, SCHEMA_ERROR,
  CONFIG_ERROR дополняют специфические STORAGE_* коды. Неизвестные HTTP-ошибки
  остаются STORAGE_ERROR, не выдаются за DNS или авторизацию.
- Исправлен доказанный тестом TypeError на нестандартном JSON `code: []/{}`:
  неизвестный upstream code отбрасывается, сохраняется безопасная HTTP-классификация.
- На существующей системной панели добавлены hostname и категория ошибки.
- Стратегия, исполнения, риски, owner authentication, scheduler, SQL, обычный
  Paper, Replay и исторические отчёты не менялись.

## Scheduler, сохранение и безопасность

Текущий `.github/workflows/aura-auto42.yml` уже использует исправленный pinned
host и `scripts/auto42_scheduler.py`. URL должен быть точно:
`https://aura-traiding-terminal.onrender.com/api/auto42/tick`.
GitHub Secrets: `AURA_AUTO42_TICK_URL`, `AURA_AUTO42_SCHEDULER_SECRET`.
Variables: `AURA_AUTO42_ENABLED=true` после проверки зависимостей.
Token должен совпадать с Render, не совпадать с owner password/DB key.

120 секунд на попытку, максимум 3 попытки с backoff, job timeout 8 минут.
Неудачный HTTP/невалидный контракт не признаётся успехом. Запуски сериализованы;
CAS/transactional RPC, operation key и candle watermark сохраняют идемпотентность.
Отсутствие БД блокирует tick/control до исполнения, нет fallback на ephemeral disk.
Состояние хранится в `auto42_account`, append-only журнал — в `auto42_events`.
Ошибка БД не создаёт фиктивный баланс и не разрешает новый вход.
GitHub cron не гарантирует точное расписание, Render Free может спать; пропущенные
слоты и свечи обрабатываются существующими безопасными ограничениями.

SQL `scripts/auto42_schema.sql` уже содержит transactional idempotent migration,
RLS/grants, три RPC и nullable saved_at. Новая миграция не нужна. Не удалять
таблицы/историю, не нажимать RESET для починки подключения.

## Android: действия владельца

1. Supabase Dashboard → проект Aura → Settings → Data API/API: скопировать
   **Project URL** (не Connection string). Сверить project-ref с проектом Aura.
2. Render Dashboard → сервис Aura → Environment: проверить **точное имя**
   `AURA_AUTO42_SUPABASE_URL`, вставить Project URL целиком без suffix.
   Наличие только `SUPABASE_URL` недостаточно. Не присылать ключи в чат.
3. В том же проекте Supabase → Settings → API Keys → legacy service_role:
   скопировать серверный ключ в `AURA_AUTO42_SUPABASE_SERVICE_KEY` Render.
   Не брать anon/publishable key или пароль PostgreSQL. Не менять ключи,
   если существующие уже соответствуют проекту.
4. Save/Rebuild/Deploy в Render для применения Environment. После commit нужен
   деплой новой версии для hostname/category UI. Агент Deploy не выполнял;
   настроенный Render Auto-Deploy может сработать на push самостоятельно.
5. Войти владельцем в Aura → открыть Aura 4.2 → Обновить. Сверить активный
   hostname с Project URL. При совпадении и DNS_ERROR после перезапуска обратиться
   в Render с временем ошибки и публичным hostname: ключи/headers не прикладывать.
   Не заменять DNS на жёстко заданный IP и не отключать TLS.
6. При SCHEMA_ERROR: резервная копия, затем SQL Editor Supabase → выполнить
   существующий `scripts/auto42_schema.sql` целиком. Проверить, что количество
   событий/портфель сохранились. При AUTH_ERROR проверить ключ/права того же проекта.
   При DATABASE_ERROR проверить здоровье PostgreSQL и PostgREST Supabase.
7. После CONNECTED проверить статус и историю, оставить режим OFF. GitHub → repo →
   Settings → Secrets and variables → Actions: задать два указанных secrets и
   включить variable. На Android при необходимости включить «Версия для ПК».
8. Actions → Aura 4.2 virtual-only scheduler → Run workflow main. При OFF ожидается
   `HEARTBEAT_OFF`, `state_saved=true`, `opened_positions=0`.
   Если есть открытая виртуальная позиция, OFF сохраняет защитное сопровождение.
   Проверить время успешного запуска и сохранения. Повторить: нет двойного входа.
9. После перезапуска сервиса проверить сохранность баланса/истории/watermark.
   Только после этих проверок можно вручную START PAPER с явным подтверждением.
   Этот аудит торговлю не активирует.

## Проверки и ограничения

Результаты тестов указаны ниже после выполнения. Все тесты offline, с dummy
credentials/mock transport. Реальные SQL/RPC, работа scheduler с production
credentials, рестарт Render и Android browser test **NOT RUN**. Публичный 401
не заменяет проверку авторизованного соединения. Система не объявляется исправленной.

- Python: **1108 passed**, 0 failed, 1 Starlette/AnyIO deprecation warning (79.58 s).
- JavaScript: **155 passed**, 0 failed (10 Node suites; auto42 suite rerun after
  adding one UI regression test).
- AST: 149 Python файлов app/scripts/tests; `import app.main`, `node --check static/auto42.js`: PASS.
- ECC module-regression и отдельные ручные code/security review passes: без изменения
  финансовых формул, без новых transport/client или authority, без снятия auth.
  Не заявляется запуск автономных ECC агентов.
- Новые тесты: ошибочный тип upstream code, категории отказов, фактический hostname,
  отсутствие fallback на generic env, отклонение REST suffix, безопасный UI hostname.
  Существующие тесты DNS/auth/DB, duplicate tick/entry, persistence/restart и paper-only
  boundary входят в полный Python/JS прогон.

Команды из корня проекта:

```sh
python -m pytest -q
for file in tests/*.cjs; do node "$file" || exit 1; done
node --check static/auto42.js
python -c 'import app.main'
```

В этой Cloud среде Python suite запускался с уже установленными pinned пакетами
через PYTHONPATH=/workspace/ecc-audit-deps:$PWD, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
`python -B`, `enable_sandbox_poll()` из scripts/replay_aura_csv.py и
`pytest.main(['-q','-p','no:cacheprovider','--tb=short'])`. Это тестовое окружение,
production event loop не менялся. Зависимости не добавлялись.

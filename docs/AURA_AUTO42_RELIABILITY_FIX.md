# Aura 4.2: исправление логирования, scheduler и диагностики

База: main `eaa83089b191c8a492a17bd95c584dc566e0f001`. Проверка: 15 октября 2026 года. **Непрерывная production-демоторговля не подтверждена.** Рабочий публичный Render API доступен; owner/Supabase проверки и новая миграция требуют владельца. Агент не менял секреты, не включал Auto Paper, не выполнял production tick и не запускал deploy.

## Подтверждённые факты и границы вывода

1. **HIGH — logging crash воспроизведён.** `app/forward/storage.py:SecretFilter.filter` безусловно делал `record.getMessage()` и `record.args=()`. Supabase 4.1/4.2 устанавливает этот фильтр на существующие handlers, включая Uvicorn access handler. `uvicorn.logging.AccessFormatter.formatMessage()` затем распаковывает пять элементов args и получает ноль: `ValueError: not enough values to unpack (expected 5, got 0)`. `start_web.py` использует стандартный `uvicorn.run`, нестандартного dictConfig не обнаружено. Ошибка access logging сама по себе не доказывает остановку приложения или причину сетевой ошибки Supabase.
2. **HIGH — неверный pinned host scheduler.** Старый workflow разрешал только `terminal.onrender.com`. Подтверждённый владельцем адрес — `aura-traiding-terminal.onrender.com`. Корректный URL этого приложения старый валидатор отвергает. Старый host в публичной проверке возвращал 404 на `/api/health` и `/api/auto42/status`.
3. **Публичная production-проверка выполнена только чтением:** на фактическом host GET `/api/health` → 200, `status=ok`; GET `/api/auto42/status` без credentials → 401. Ответы заняли около 31.46 s. Это подтверждает доступность API и owner boundary, но **не** подключение к БД, работу стратегии или cold-start SLA.
4. Через GitHub получены metadata последних пяти ручных запусков — все failure. В job `116327576600` / run `38706641417` финальное сообщение — `Invalid scheduler configuration`; в job `116330091026` / run `38707394894` — `Demo not operational; inspect owner dashboard`. Старый код скрывает конкретную HTTP/network/API причину второго сбоя. Значения secrets не читались и не выводились; нельзя установить, какие именно значения были заданы в каждом историческом запуске.
5. **MEDIUM — `STORAGE_NETWORK` слишком общий.** Он объединял httpx transport failures DNS/TLS/connect/read/proxy/protocol. HTTP 401/403 уже обрабатывались отдельно; эта метка сама по себе **не означает неправильный пароль**. Точную транспортную причину Render→Supabase в текущей сессии установить нельзя: нет server key, owner password, Render logs или приватного доступа к выбранному project. Новая диагностика должна показать конкретный класс следующего сбоя.
6. **MEDIUM — transient pause не восстанавливалась без позиции.** После временной ошибки mode становился PAUSED, но следующие ticks не читали рынок, если позиции нет. Добавлен отдельный persisted recovery flag только для ранее активированного ON, остановленного по allowlist временных ошибок. Старые PAUSED без этого флага консервативно требуют owner START.

## Что изменено

- Фильтр секретов сохраняет шаблон, args tuple/dict и типы чисел (включая HTTPStatus), редактирует строковые/bytes значения, traceback и stack. Access/application diagnostics не отключаются. Изменение общего фильтра касается 4.1 тоже; его policy hash создаст отдельную cohort будущих записей. Старые forward rows и результаты не переписываются; artifact 4.0 совместим.
- Supabase adapter различает STORAGE_DNS/TLS/CONNECT/READ/WRITE/PROXY/PROTOCOL/NETWORK/TIMEOUT. Безопасные HTTP status и закрытый PostgREST/Postgres code allowlist различают auth, permission, schema missing, rate limit и DB connection pool. Полные URL, headers, message/details/hint и exception text не возвращаются.
- API отдаёт безопасную component diagnostics и имена недостающих/неверных переменных. Успех HTTP маршрута не равен успеху БД или обработке свечи. Нет автоматических изменений credentials, обхода TLS, proxy или скрытого fallback в SQLite.
- `scripts/auto42_scheduler.py` — testable stdlib client. Workflow использует его через pinned checkout, contents:read и persist-credentials:false. Проверяется фактический Render host и точный путь. Timeout 120 s, максимум три попытки, backoff 2/4 s, job ≤8 min. Auth, schema и неверный URL не повторяются бессмысленно. Redirects запрещены. Ошибки выводят только HTTP и безопасный код.
- Tick contract содержит `state_saved`, `tick_outcome`, `processed_this_run`, `last_processed_closed_at`, `decision`, counts открытий/закрытий. HEARTBEAT_OFF/NO_NEW_CANDLE/NO_NEW_WORK не выдаются за расчёт новой свечи. CANDLE_PROCESSED с WAIT и нулём входов — корректный результат. HTTP 200 без данного контракта недостаточен: client сообщает API_CONTRACT_MISMATCH.
- Recovery не создаёт новую owner-авторизацию. Прежний ON может восстановиться только после нового coherent fresh snapshot; pending удаляется при сбое, старый сигнал не исполняется повторно. STOP/EMERGENCY сбрасывают recovery authority. Daily loss, drawdown, gaps/corrections и unconfirmed data по-прежнему блокируют входы. Risk pause не rearm автоматически. Финансовые формулы, thresholds, fee/slippage и SL/TP не изменены.
- Добавлены десять полей «СОСТОЯНИЕ СИСТЕМЫ»: Render API, Supabase, подтверждённый tick, closed candle, decision, error, actual save timestamp, Auto Paper, protection, block reason. ONLINE относится к ответу API; CONNECTED — к актуальному Supabase RPC. Локальная SQLite не выдаётся за подключение Supabase. Сетевой сбой браузера означает UNKNOWN, а не доказанный OFFLINE сервера. Старые evidence после 120 s не отображаются как актуальная успешная проверка. Времена помечены UTC.

## Хранилище и безопасная миграция

Aura использует **Supabase HTTPS/PostgREST RPC**, а не прямое подключение к PostgreSQL по connection string/5432. Нужны project HTTPS URL и server service-role key, не DB password. Не вводите `postgres://...` в AURA_AUTO42_SUPABASE_URL.

`scripts/auto42_schema.sql` теперь является транзакционной идемпотентной миграцией: добавляет nullable `saved_at`, обновляет load/commit envelopes и уведомляет PostgREST о schema reload. На существующих rows исторический timestamp остаётся NULL/UNKNOWN, не выдумывается. Только новая фактически подтверждённая запись обновляет timestamp по часам БД. Append-only events, payload/hash, balances, trades и revision не сбрасываются миграцией. Trigger пересоздаётся внутри одной DDL-транзакции; таблицы и журнал не удаляются. SQLite dev получает эквивалентный additive column migration, проверенный тестом.

**Реальное исполнение PostgreSQL SQL/RPC здесь NOT RUN:** PostgreSQL и credentials отсутствуют. До использования владельцу нужно проверить SQL на своём project. Предварительно сохраните backup и зафиксируйте revision/hash/count:

```sql
select revision, sha256 from public.aura_auto42_account where id = 1;
select count(*) as journal_events from public.aura_auto42_events;
```

Выполните актуальный `scripts/auto42_schema.sql` в Supabase SQL Editor. Повторите запросы: без параллельных ticks revision/hash/count должны совпасть. Для проверки новой metadata:

```sql
select revision, sha256, saved_at from public.aura_auto42_account where id = 1;
```

Не делайте RESET DEMO, DELETE, TRUNCATE, ручной UPDATE payload или замену database ради исправления связи. При STORAGE_SCHEMA_MISSING проверьте нужный project и применённые RPC; при STORAGE_PERMISSION_DENIED — grants service_role/RLS; при STORAGE_AUTH — server service key; при STORAGE_DNS — корректный активный project hostname; при STORAGE_TLS — trust/сертификат без отключения verification; при STORAGE_DATABASE_UNAVAILABLE — состояние проекта/DB pool. Одна лишь UI-ошибка не доказывает конкретную причину.

## Точные настройки владельца

GitHub repository → Settings → Secrets and variables → Actions:

| Тип | Имя | Значение/назначение |
|---|---|---|
| Secret | `AURA_AUTO42_TICK_URL` | `https://aura-traiding-terminal.onrender.com/api/auto42/tick` |
| Secret | `AURA_AUTO42_SCHEDULER_SECRET` | Отдельный случайный ASCII token 32–256 символов, без newline |
| Variable | `AURA_AUTO42_ENABLED` | `true` только после owner setup; сам по себе не включает портфель |

Render → Aura service → Environment:

- `AURA_AUTO42_SUPABASE_URL`: `https://<project-ref>.supabase.co`, без пути, slash, query, userinfo.
- `AURA_AUTO42_SUPABASE_SERVICE_KEY`: server service-role key, не anon key и не DB password.
- `AURA_AUTO42_SCHEDULER_SECRET`: точно совпадает с одноимённым GitHub Secret; отличается от owner password, DB key и forward token.
- `AURA_TESTNET_VIEW_PASSWORD`: существующий owner password (не менее 12 символов), не передаётся в Actions.

`AURA_AUTO42_SQLITE_PATH` на Render отсутствует. PORT задаётся Render, запуск остаётся `python start_web.py`, 0.0.0.0. Биржевые ключи для этого режима не нужны и не читаются. Никакие значения владельца не менялись автоматически. Без private config нельзя честно указать, какая именно переменная вашего Render сейчас неправильная: новая owner-панель сообщает проверяемые имена/ошибки.

## Один ручной tick и проверка restart

1. Дождитесь выкладки исправленного backend обычным владельческим процессом. Агент deploy не выполнял. При включённом Render auto-deploy push может инициировать его по вашей существующей настройке.
2. В owner-панели проверьте фактический режим. Для smoke без входов владелец сам выбирает STOP; при открытой позиции защитный settlement остаётся возможен, это нужно учитывать. Не сбрасывайте портфель.
3. Откройте «СОСТОЯНИЕ СИСТЕМЫ». API ONLINE и Supabase CONNECTED должны быть результатом текущего owner-запроса. Запишите epoch, revision, balance, position/trade counts, watermark и saved_at. Никому не отправляйте ключи.
4. GitHub → Actions → **Aura 4.2 virtual-only scheduler** → Run workflow → main. Включение repository variable разрешает workflow, но не START PAPER.
5. Успешный OFF smoke: `outcome=HEARTBEAT_OFF processed=False opened=0`. ON без сигнала: `outcome=CANDLE_PROCESSED decision=NO_CONFIRMED_SETUP processed=True opened=0`. Это не ошибки. `API_CONTRACT_MISMATCH` обычно означает, что workflow уже новый, а backend ещё старый.
6. После run проверьте новый подтверждённый tick и сохранение. Повтор внутри того же 5-минутного slot даёт NO_NEW_WORK и не создаёт второе исполнение. В другом slot допустима новая TICK-запись, но не повторный вход по одной свече.
7. Владелец перезапускает Render. После owner read должны сохраниться epoch, balance, PnL, trades и позиция, без повторного входа. Время save не должно обновляться от одного чтения. Нет подтверждённого сохранения — не считать restart recovery успешным.
8. START выполняет только владелец после проверок. WAIT не исправляют искусственными сделками и ослаблением условий. Непрерывность GitHub cron/Render Free не гарантируется; следите за last tick и missed slots.

Для локального ручного client запуска, если credentials уже безопасно заданы в environment:

```bash
python scripts/auto42_scheduler.py
```

Не передавайте token аргументом CLI и не включайте verbose HTTP/debug headers. Script фиксирует target host и не отправляет данные на биржу.

## Проверки и review

Полный Python suite: **1091 passed**, 0 failures/errors/skipped, 1 deprecation warning, 76.24 s. Новых Python-тестов: **26**. Полный Node suite: **154 passed**, 10 файлов, 0 failed; новых UI-тестов 3. Syntax — 154 Python файла, imports, JavaScript и workflow YAML — PASS. Pinned checkout commit проверен в официальном actions/checkout. Статический поиск secrets/write endpoints: совпадений в изменённом runtime-коде нет; это не полноценный security scanner. Ruff/mypy/bandit отсутствуют — NOT RUN. Машинная сводка: `docs/AURA_AUTO42_RELIABILITY_VERIFICATION.json`. Проверены реальные logging records Uvicorn, tuple/dict/HTTPStatus, secret redaction, mocked DNS/TLS/HTTP/schema/permissions, additive SQLite migration, timestamps/restart, scheduler config/timeout/retries/contract, WAIT/no duplicate entries, transient recovery authority и owner UI errors. Fixtures синтетические и используются только для проверки программ, не доходности.

Отдельные code/security/trading-safety review passes выполнены по существующим ECC/Aura guidance одним исполнителем. Нативные ECC agents/hooks не запускались. Защитные контуры реальных ордеров и старые Paper/Replay/history не менялись.

**NOT RUN:** приватный Render owner запрос, реальный Supabase RPC/SQL/grants/TLS path из Render, фактическая доставка нового workflow, production restart и Android Chrome layout. Публичный GET smoke описан отдельно и не заменяет этих проверок. Отчёт не утверждает, что STORAGE_NETWORK в production уже устранён: конкретная транспортная причина требует следующей безопасной diagnostics.


## Состав коммита и воспроизведение

- Backend: `app/forward/storage.py`, `app/automated/{api,engine,service,storage,diagnostics}.py`.
- Scheduler/schema: `.github/workflows/aura-auto42.yml`, `scripts/auto42_scheduler.py`, `scripts/auto42_schema.sql`.
- UI: `static/auto42.js`, `static/index.html`.
- Tests: `tests/test_auto42_diagnostics.py`, `tests/test_auto42_scheduler.py`, `tests/test_auto42_frontend.cjs`.
- Документы: этот отчёт, `docs/AURA_AUTO42_RELIABILITY_VERIFICATION.json`, исправленный deployment URL в `docs/AURA_AUTO_PAPER_TRADING_4_2.md`.

```bash
python -m pytest -q
node --test tests/*.cjs
node --check static/auto42.js
python -c "import app.main"
```

В cloud использовались уже установленные pinned зависимости из `/workspace/ecc-audit-deps` и test-only `scripts.replay_aura_csv.enable_sandbox_poll()` с отключённым pytest plugin autoload. Runtime event loop не менялся. Frontend — plain HTML/JS, отдельной сборки нет. PostgreSQL не установлен, SQL execution не выдаётся за PASS. Предыдущие research reports/истории сохранены.

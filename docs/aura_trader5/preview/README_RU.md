# Изолированный Render Free preview — Aura Live Manual Trader 5.0

**Подготовлено, не создано и не развёрнуто.** Все действия ниже выполняются только
после отдельного разрешения владельца на новые ресурсы, SQL и первый deploy.
Production, существующие env, Active43, scheduler и Supabase-таблицы не изменялись.

## Выбранная архитектура

Обычный отдельный Render **Free Web Service**, привязанный к ветке PR #62, с
`app.manual_preview.main:app`. Это не production service preview/duplicate и не
автоматический Preview Environment. У него собственные URL, пароль и env.
Не используется `start_web.py`, `app.main` и их lifespan. В приложении нет
Active43/Auto42/Practice routers, торгового scheduler, приватных exchange API,
реальных ордеров или права менять production PAPER.

Хранилище — **отдельный новый Supabase Free project**. Другая схема или таблица
в рабочей Aura DB не считается достаточной изоляцией. SQLite и Render Free
Postgres не выбраны: SQLite на Free исчезает при restart/sleep, а Free Render
Postgres истекает через 30 дней. Persistent disk у Free Web недоступен.

Привилегированный ключ нового preview-проекта находится только в серверном env.
Браузер получает только результаты аналитики/виртуального счёта и использует
отдельный owner Basic login. Никаких Supabase или Bitget торговых ключей в JS.
Рыночные данные — публичные Bitget USDT-M BTCUSDT REST/WS.

## Что проверено в инфраструктуре read-only

28.10.2026 metadata API показали один существующий Render Web Service production:
Free, branch main, autoDeploy=no/off. Отдельного preview ещё нет. Supabase metadata
показали один project Aura ACTIVE_HEALTHY. Это не проверка оставшейся квоты или
billing-доступа на создание ресурсов. Значения env/ключей не читались; SQL через
Supabase не выполнялся. Новые ресурсы не создавались.

В коде явно запрещены известные production project ref и Render service ID/host.
Generic/production `AURA_*`, `SUPABASE_*`, биржевые credentials, Render/GitHub/CF
deployment tokens в окружении preview запрещены. Нельзя подключать production env
набор или копировать настройки существующего сервиса.

## Защита хранилища

1. Новый project ref ровно 20 lower-case alphanumeric символов. URL должен быть
   точно `https://<тот же ref>.supabase.co`, redirects запрещены. Production ref
   заблокирован до создания HTTP-клиентов.
2. Рекомендуется новый `sb_secret_...` ключ **только нового проекта**. Чужой ключ
   не проходит аутентификацию на закреплённом preview host. До любой ledger RPC
   выполняется только read-only guard. Это не угадывание принадлежности opaque
   ключа по его значению: её проверяет Supabase на правильном host.
3. Legacy service_role JWT тоже поддерживается, но его ref/role/expiry должны
   соответствовать preview ещё до сети. Парсинг JWT не является проверкой подписи;
   подпись и роль проверяет Supabase. Новые opaque keys предпочтительнее согласно
   текущей документации Supabase; legacy не требуется.
4. SQL pack отказывается работать в непустом public schema без preview-marker,
   даже если там только существующий Manual Paper. Reapply разрешён только с
   тем же marker/ref и тремя разрешёнными preview-таблицами. Наличие чужой таблицы
   блокирует setup/attestation. Балансы не сбрасываются.
5. Перед **каждым** load/lookup/commit/init повторяется read-only RPC
   `aura_manual_preview_guard`. Scope/ref/role должны совпасть, isolated=true.
   Нет fallback на production DB, SQLite или другой ключ.
6. Guard — SECURITY INVOKER, только SELECT. Marker service_role может читать,
   но не менять. anon/authenticated не имеют доступа к ledger/guard. Manual RPC
   и атомарные receipts — существующий проверенный механизм из #57.

Бизнес-назначение произвольного пустого проекта невозможно узнать из opaque
ключа offline. Поэтому новый отдельный проект и проверка его ref в Dashboard —
обязательное предусловие владельца. Известный production не разрешается ни при
каком значении preview flag. Нельзя вручную добавлять marker в рабочую БД.

## Подготовленные файлы

- [`deploy/manual-preview/render.yaml`](../../../deploy/manual-preview/render.yaml):
  отдельный Free service, ветка PR #62, один worker процесса, health `/api/health`.
  `autoDeployTrigger: off` — актуальный эквивалент API `autoDeploy=no`.
  Нет database resource, disk, envGroup, Cron, preDeploy SQL или initial seed hook.
  JSON-синтаксис файла является валидным YAML. Проверен текущей официальной JSON
  Schema Render. Platform validation/создание не проводились.
- [`deploy/manual-preview/schema.sql`](../../../deploy/manual-preview/schema.sql):
  полный готовый pack для нового пустого preview Supabase. Не применяется кодом.
- [`app/manual_preview/`](../../../app/manual_preview/): отдельное приложение,
  project/key/env gates, владелец на UI/static/API, allowlist assets и DB guard.
- [`scripts/verify_manual_preview_postgres.py`](../../../scripts/verify_manual_preview_postgres.py):
  только временный локальный Docker PostgreSQL с network=none.
- [`scripts/verify_manual_live_browser.py`](../../../scripts/verify_manual_live_browser.py)
  с `--preview`: actual preview HTML/API, dummy quotes, отдельная SQLite, desktop/touch.

## Цена и ограничения

**Плановая дополнительная стоимость: $0/месяц** при доступных Free ресурсах и
соблюдении квот. Платные сервисы и subscriptions в конфигурацию не включены.
Возможность открыть бесплатные ресурсы без дополнительной проверки аккаунта
не подтверждена; owner должен проверить предложение Free перед созданием.

| Компонент | Бесплатные ограничения / риск |
|---|---|
| Render Free Web | 0.1 CPU, 512 MB; sleep после 15 минут без inbound traffic; cold start около минуты; локальный диск ephemeral |
| Render workspace | **750 instance-hours на весь workspace**. После исчерпания останавливаются все его Free Web Services. Production + preview 24/7 не помещаются в 750 часов |
| Render bandwidth/build | Общие квоты; возможны overage charges при payment method или suspension без него. Не подключать keep-alive и Cron; проверить spend limit и квоты |
| Supabase Free | 500 MB DB, до 2 active Free projects по текущим правилам; pause после недели неактивности; slot/billing проверить перед созданием |
| SL/TP | Виртуальные проверки раз в 5с только пока сервер работает. При сне/паузе DB/недоступности API выход задерживается и может пропустить внутрипериодное касание; это не биржевой стоп |

**Рекомендация: отдельный Hobby Render workspace**, если он доступен бесплатно
по правилам аккаунта. Это разделяет resource/quota risk от рабочего workspace.
Если бесплатно создать его нельзя, не обещать полную ресурсную изоляцию и не
размещать preview рядом с production без отдельного согласования квот. У текущего
workspace остаток 750 часов не проверен. Даже короткие тесты расходуют общую квоту.

Если новый Supabase Free slot недоступен — **BLOCKED**, не использовать рабочий
проект и не оформлять платную замену автоматически. Не обещается 24/7 работа.

## Env — только нового preview-сервиса

| Имя | Значение / источник |
|---|---|
| `PYTHON_VERSION` | `3.12.14` |
| `AURA_PREVIEW_ONLY` | `true`, обязательная защита entrypoint |
| `AURA_PREVIEW_MANUAL_ENABLED` | **false** при первом deploy; true только отдельно разрешённым действием в preview после проверок |
| `AURA_PREVIEW_OWNER_PASSWORD` | Новый уникальный пароль ≥16 ASCII символов; только Render Secrets; не production owner password |
| `AURA_PREVIEW_PROJECT_REF` | Ref нового пустого preview Supabase |
| `AURA_PREVIEW_SUPABASE_URL` | `https://<preview-ref>.supabase.co` |
| `AURA_PREVIEW_SUPABASE_SERVICE_KEY` | Secret key только нового проекта, только сервер; значение не печатать |

Никаких существующих env не редактировать и не копировать. Не нужны Bitget private
keys, Render API token, Cloudflare token, Supabase PAT или GitHub token в runtime.
Render `PORT` задаёт платформа. Приложение слушает 0.0.0.0. Proxy headers доверяются
Render edge: не публиковать listener напрямую за другим недоверенным proxy.

## Пошаговый запуск — только после отдельного разрешения

1. **Ресурсы и квоты.** [Render Dashboard](https://dashboard.render.com/) — выбрать
   новый отдельный бесплатный Hobby workspace, проверить квоты/spend limit.
   [Supabase Projects](https://supabase.com/dashboard/projects) — создать **новый**
   Free project для preview, если slot доступен. Сохранить его ref, не production.
   Ничего этого в текущей задаче не создавалось.
2. **SQL нового проекта.** Открыть SQL Editor именно нового проекта. В начале
   [`schema.sql`](../../../deploy/manual-preview/schema.sql) заменить единственный
   `REPLACE_PREVIEW_PROJECT_REF` на ref нового проекта, вставить весь pack.
   До замены pack преднамеренно падает до CREATE. После применения ожидаются три
   `aura_manual_*` таблицы и guard/RPC; никаких существующих Aura таблиц.
   Требуются права SQL owner нового проекта. Не запускать pack в Aura production.
3. **Новый Render service.** Создать отдельный Web Service/Blueprint с именем
   `aura-manual-trader5-isolated-preview`, repo DOK123123/Aura-Traiding-Terminal,
   branch `feature/aura-live-manual-trader5`, path `deploy/manual-preview/render.yaml`.
   Проверить Free и auto-deploy OFF; задать только env из таблицы. Не нажимать
   Duplicate/Preview у production. **Создание Blueprint запускает первый deploy
   даже с autoDeploy=off** — этот шаг требует разрешения и на deploy.
4. **Проверка без сделок.** Убедиться в нужном commit SHA и отдельном URL.
   `/api/health`: scope `ISOLATED_MANUAL_PREVIEW`, реальные ордера false,
   automatic-entry scheduler false. Открыть `/`, войти `aura` с новым preview
   паролем. Видны PREVIEW banner, LIVE-график и два профиля, нет Active43.
   Нажать «Проверить preview · только чтение». Нужны Bitget CONNECTED,
   ISOLATED_SCOPE_CONFIRMED, state_changed=false; Manual Paper остаётся OFF.
   Диагностика не создаёт счёт и не вызывает protect/tick.
5. **Отдельное разрешение на виртуальные операции.** Только после пункта 4
   разрешить `AURA_PREVIEW_MANUAL_ENABLED=true` **на preview** и ручной deploy
   preview. Открытие панели счёта создаст новый виртуальный баланс 10000, если
   его ещё нет; существующий preview account восстанавливается, не сбрасывается.
   Выбрать маленькое количество, корректные SL/TP, нажать BUY/SELL и подтвердить.
   Условный WAIT-план не копируется как готовая рекомендация. Подтверждение OPEN
   также явно разрешает автоматические защитные SL/TP. Ручной CLOSE требует
   отдельного подтверждения; отмена диалога не отправляет POST.
6. **Сохранение/restart.** Записать preview position ID, version и balance из
   owner state. Для специально согласованного restart-теста перезапустить только
   preview и проверить тот же ID/баланс. Затем CLOSE, убедиться в одной записи
   CLOSED, fees/PnL и уникальном receipt. SQL Editor только нового проекта:
   `SELECT version, saved_at FROM public.aura_manual_paper_v1_account;`
   `SELECT request_id, receipt->>'command' FROM public.aura_manual_paper_v1_requests ORDER BY created_at;`
   Не редактировать payload. Удалённый restart/SLTP пока NOT VERIFIED.

Права: создание отдельных ресурсов, запись env только нового сервиса, SQL owner
и чтение API key только нового проекта. Права на изменение production не нужны.
При отсутствии любого предусловия остановиться, не обходить guard.

## Ошибка, остановка и откат

Не включать Manual до успешной read-only проверки. При 401/503/scope mismatch
новые операции блокируются, нет fallback/reset. Проверить только preview ref,
scope SQL и ключ нового проекта. Не брать production service_role «для проверки».

При открытой preview-позиции не выключать защитный worker ради выключения UI.
После восстановления свежих данных закрыть позицию штатным CLOSE, сверить
receipt, затем отдельно выключить preview manual flag/сервис. При намеренном
restart тесте учитывать отсутствие гарантии защитных fills во время паузы.

Rollback — вручную прежний **preview** SHA с совместимой схемой или остановка
нового preview после закрытия его позиций. Не откатывать production. SQL rollback
с DROP не поставляется; не удалять аккаунт/журнал. DB не откатывается вместе с
кодом. Перед удалением disposable проекта отдельно сохранить его нужные данные.

## Доказательства и оставшиеся ограничения

См. `VERIFICATION.json`, `BROWSER.json`, public market probe и описание PR для
результатов финального CI. Локально проверены реальные PostgreSQL роли/RLS,
отказ на чужой DB, reapply без сброса, restart, owner/confirmation, LONG/SHORT,
TP/SL, PnL и отсутствие авто-router. Actual Uvicorn restart сохраняет счёт.
Браузер использует actual preview page/API с тестовыми котировками и SQLite,
это не доказательство hosted Supabase или Render. Физический Android не доступен.
Новый preview не создан: **RENDER_PREVIEW_VERIFIED=false**,
**HOSTED_PREVIEW_SUPABASE_VERIFIED=false**, реальные env/SQL/deploy не менялись.

Источники проверены 28.10.2026:
[Render Free](https://render.com/docs/free),
[Blueprint spec](https://render.com/docs/blueprint-spec),
[Deploys](https://render.com/docs/deploys),
[Health checks](https://render.com/docs/health-checks),
[Supabase Pricing](https://supabase.com/pricing),
[Supabase API keys](https://supabase.com/docs/guides/api/api-keys).
Legacy keys deprecated, новые secret keys поддерживаются. Тарифы/доступность
могут меняться, billing и региональная регистрация в этой задаче не тестировались.

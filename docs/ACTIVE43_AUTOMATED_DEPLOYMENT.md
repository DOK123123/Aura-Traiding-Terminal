# Aura 4.3: публикация через GitHub с Android

Ничего не активировано этим PR. Workflow выключен, пока владелец явно не установит
repository variable `AURA_PRODUCTION_DEPLOY_ENABLED=true`. Merge, deploy, создание
ключей, изменение production и PAPER разработчиком не выполнялись.

## Что станет автоматическим

После push/merge в main workflow `Regression CI` обязан успешно проверить **точный
merge SHA**. Затем `Aura 4.3 Production Deployment`:

1. Проверяет актуальный main, источник push/main своего репозитория, workflow ID,
   успешный единственный regression job и реально выполненные regression/report
   steps. В существующем CI `ci/check_results.py` отклоняет skipped/пустые/failed
   Python и Node отчёты. PR CI не подменяет CI merge-коммита.
2. Проверяет существующий Render Web Service: repo/branch/URL, Auto-Deploy OFF,
   отсутствие активного другого deploy. Фиксирует текущий Live SHA для отката.
3. Авторизованным GET проверяет сохранённый PAPER OFF, отсутствие позиции/pending/
   recovery и точный риск guard. Хеширует финансовую часть состояния и **всю OPEN/
   CLOSE историю текущего epoch** через peek + существующий SELECT-only RPC. До
   4000 записей каждого типа/40с; при лимите, ошибке или изменении revision BLOCKED.
   Никаких seed/load/adopt, tick/START/STOP/RESET, SQL и записей счёта.
4. Проверяет **существующий** Worker `aura-ctive43-scheduler`: 100% одна активная
   версия, latest uploaded совпадает с active, Cron `2-59/5 * * * *`, строковые
   bindings saved_mode/true, scheduler secret присутствует. Читает settings,
   schedules, subdomain и immutable version resources; не публикует их
   значения в логи/artifact. Не поддерживаемые настройки требуют ручного review.
5. Deploy Render через API с `commitId=<точный SHA>`, без очистки cache/env/БД.
   Ждёт Live, HTTP200 health и совпадение фактического `render_commit` из
   авторизованного read-only gate. Пока это не подтверждено, Worker не меняется.
6. Через Cloudflare Versions API загружает единственный module из checkout main.
   Полный binding inventory наследуется по имени через `inherit` и
   `bindings_inherit=strict`; значения secrets не читаются и не отправляются.
   Runtime копируется из текущих настроек, вместо небезопасного repo wrangler
   config. Проверяет неизменность всех binding/runtime ресурсов staged версии и
   settings/Cron/subdomain. Лишь затем переключает **тот же Worker** на
   новую Version UUID с трафиком 100%. Не вызывает create-script, routes/settings/
   secrets/schedules update, не создаёт Worker или инфраструктуру.
7. Ждёт до 17,5 минут два **автоматически сохранённых** OFF/COMPLETED tick в соседних
   слотах после активации Worker: разные ID, source attribution и origin Render
   SHA. Читает реальные immutable Supabase receipts через backend, не вызывает
   tick сам. Проверяет полную PAPER readiness/свежесть 5m и сохранность ledger.
8. Пишет `deployment-report.json`, безопасный Actions Summary, rollback SHA/UUID,
   фактический Render SHA, исходный worker source SHA256 и два tick ID/UTC.

`outcome=ok`, произвольный HTTP200 и ручная диагностика не заменяют receipt.
Attribution — доверенное сообщение клиента с scheduler auth + фактический
immutable SQL receipt. Это не независимый Cloudflare audit и не подтверждение,
что клиент получил HTTP200 и вывел TICK_SAVED: эти поля в отчёте остаются false.
Независимое подтверждение платформенных логов потребует отдельно разрешённого
read-only доступа к Cloudflare Observability; такого доступа в задаче нет.

Routes сохраняются по контракту Versions/Deployments API: версия меняется у того
же имени, routing API вообще не вызывается. Zone-scoped route inventory не
считывается без дополнительных разрешений/Zone ID; `route_inventory_verified=false`
явно записывается в отчёт. Это не выдуманная независимая сверка списка routes.

## Однократная настройка с Android (после разрешения владельца)

Никакие значения ключей не отправляйте в ChatGPT, inputs, issues или PR.

### 1. GitHub Environment и Secrets

Откройте https://github.com/DOK123123/Aura-Traiding-Terminal/settings/environments
и создайте/выберите environment **production**. **Обязательно** выберите Deployment
branches and tags → Selected branches and tags → добавить только branch `main`.
Не оставлять All branches: без ограничения веток нельзя безопасно выдавать
production Secrets ручным запускам изменяемых workflow. Job дополнительно
проверяет github.ref=refs/heads/main и через GitHub read-only API требует
единственную environment branch policy `main`; при All branches публикация
блокируется. Эти API используют встроенный GITHUB_TOKEN с Actions read, новый PAT
не требуется. Это не замена правильной настройки environment до выдачи Secrets.
Для первого запуска рекомендуется required reviewer, если он доступен тарифу.
При обязательном reviewer Actions будет ждать нажатия Approve; это осознанная
защита, не полностью безусловный auto-deploy. Впоследствии политика одобрения —
решение владельца; код её не отключает.

Добавьте **три** Environment Secrets:

| Название | Откуда взять |
|---|---|
| `AURA_RENDER_API_KEY` | Render Account Settings → API Keys: https://dashboard.render.com/u/settings |
| `AURA_CLOUDFLARE_API_TOKEN` | https://dash.cloudflare.com/profile/api-tokens → минимальная Editor/Workers Scripts Edit роль для существующего Worker/аккаунта с чтением его метаданных. Не Global API Key; Zone Routes Write не нужен. Если API не позволяет такую минимальную область, остановиться и проверить требуемый scope, не расширять до admin автоматически. |
| `AURA_TESTNET_VIEW_PASSWORD` | Уже действующий пароль Owner Panel из Render; не создавать новый пароль |

`GITHUB_TOKEN` предоставляет GitHub автоматически (contents/actions read).
**Не нужны** Supabase service key, торговые Bitget ключи и копия scheduler secret.
Render API key может иметь широкую область действия: хранить только в защищённом
production environment. Токен Cloudflare — control-plane, не торговый ключ.
Новых платных ресурсов и подписок workflow не создаёт; расходует существующие
GitHub Actions/build/API квоты. Тарификация существующих аккаунтов остаётся их
обычной; абсолютная бесплатность не гарантируется при превышении квот.

### 2. Repository Variables

Откройте https://github.com/DOK123123/Aura-Traiding-Terminal/settings/variables/actions
и добавьте:

- `AURA_RENDER_SERVICE_ID`: ID **существующего** Web Service вида `srv-...` из
  его адреса/Settings в Render. URL должен быть aura-traiding-terminal.onrender.com.
- `AURA_CLOUDFLARE_ACCOUNT_ID`: Account ID существующего Worker (32 hex).
- `AURA_PRODUCTION_DEPLOY_ENABLED`: сначала `false`; `true` только при отдельном
  разрешении владельца на автоматические будущие публикации после CI/merge.

В Render Auto-Deploy должен оставаться OFF: иначе независимый Render deploy
обойдёт порядок этого workflow. Контроллер проверяет это, но сам env/settings
Render не меняет. В Cloudflare оставить saved_mode/true/Cron/routes/secrets как есть.
Не подставлять `deploy/active43-free-worker/wrangler.jsonc` — его имя и defaults
предназначены для другого сценария.

### 3. Первый безопасный запуск: bootstrap и проверка

Новый `/api/active43/deployment-readiness` должен **уже существовать в Render до
первого автоматического deploy**: он нужен для надёжного pre-deploy baseline и
полной проверки истории. Старый backend его не предоставляет. При HTTP404/401
workflow **заблокируется до любых изменений**, а не обойдёт проверку.

Workflow появится в списке Actions только после merge файла в main. До merge
отсутствие этой кнопки/страницы ожидаемо; feature-ветка не публикует production.

После разрешённого merge и зелёного push/main CI:

1. Пока PAPER OFF, выполните существующую read-only OFF-only проверку в Owner
   Panel. Если нового release-gate ещё нет, **один раз** вручную опубликуйте этот
   проверенный main в существующем Render через Manual Deploy → Deploy specific
   commit. Это отдельное разрешённое bootstrap-действие владельца, не выполненное
   данным PR. Не менять env/SQL/Worker/PAPER. Безопасно автоматизировать precheck
   отсутствующего endpoint без дополнительного production доступа невозможно;
   Supabase admin-key в GitHub для обхода этого ограничения не требуется.
2. После проверки нового backend и добавления Secrets/Variables установите
   deploy enabled=true (если разрешена дальнейшая автоматизация). Откройте
   https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/production-deploy.yml
   → Run workflow, main, operation=deploy, `ci_run_id` оставить пустым: контроллер сам найдёт успешный **push/main**
   Regression CI точного checkout SHA. Если уже Live тот же SHA, Render повторно не пересобирается.
3. При настроенном reviewer нажмите Approve. Дождитесь DEPLOY_VERIFIED и artifact:
   Render SHA, Worker Version UUID, два разных автоматических tick ID. PAPER
   должен остаться OFF; включение требует отдельного разрешения.

После bootstrap дальнейшие merge → успешный main CI → Render → Worker → receipt
проверки идут без ручного копирования JS. Владелец только соблюдает выбранную
политику approval. При PAPER ON публикация блокируется: workflow **не выключает**
торговлю автоматически ради deploy.

## Откат с телефона

Не выполняется автоматически при ошибке: безопаснее сохранить совместимый старый
Worker/новый backend, чем делать повторный слепой POST при неизвестном результате.

1. В Actions Summary/artifact текущего release найдите `previous_render_commit`
   и `previous_worker_version_id`. Эти безопасные ID также выводятся checkpoint
   до публикации, на случай жёсткой отмены runner до загрузки artifact.
2. Run workflow → main → operation=rollback. `ci_run_id` можно оставить пустым для поиска CI текущего main; укажите оба точных rollback ID и подтверждение
   `ROLLBACK PAPER OFF NO CONFIG ROTATION`. Требуются PAPER OFF, пустая позиция/
   pending, неизменность текущей истории во время отката и **отсутствие ротации
   secrets/bindings после выбранной версии**. Secret values не читаются API;
   одинаковые имена не доказывают отсутствие ротации — это подтверждает владелец.
3. Контроллер проверит target SHA в истории данного Render и в предках main,
   совместимый binding/runtime profile данной Worker Version. Откатит сначала
   Worker, затем Render, сохраняя текущую БД. При несовпадении профиля/отсутствии
   read-only gate/CI/неизвестном результате остановится для ручной проверки.

Если автоматический rollback BLOCKED: Cloudflare → **тот же** Worker → Deployments
→ Rollback на **точную** UUID; Render → тот же Web Service → Manual Deploy → exact
previous SHA. Не делать RESET, SQL, ротацию ключей или PAPER ON. После отката на
backend без нового gate независимая проверка через Owner Panel обязательна;
автоматическую процедуру, не имеющую endpoint, нельзя объявлять подтверждённой.

## Ограничения и безопасность

- Один GitHub concurrency group для release/rollback; cancel-in-progress=false.
  Другие deploy-инструменты и внешнее ручное изменение счёта/настроек должны быть
  приостановлены владельцем. Read-only проверки не являются распределённой
  транзакцией между GitHub/Render/Cloudflare/Supabase; есть TOCTOU окно. Если
  владелец параллельно включает PAPER, workflow остановится при следующем чтении,
  но не имеет права автоматически остановить торговлю. Не утверждается обратное.
- GET повторяется ограниченно с учётом Retry-After. POST не повторяется: при timeout
  исход неизвестен; сверить Render/Cloudflare по baseline и staged UUID. Уже
  загруженная, но не активная версия требует review; workflow не удаляет её.
- Без доступа/валидных Secret workflow BLOCKED. Реальные провайдерские deploy API
  в разработке не вызывались. Tests используют fake APIs и настоящий локальный
  PostgreSQL. Совместимость protocol проверена; фактическая API-схема и permissions
  текущих аккаунтов должны быть подтверждены первым разрешённым запуском.
- После отката старый Worker может перестать сохранять scheduled attribution;
  receipt readiness станет BLOCKED, а не искусственно READY. Free Render может
  засыпать; GitHub/Cloudflare/Render не дают гарантии 24/7 по результату двух ticks.
- Никаких strategy/risk/SQL/env изменений, биржевых методов и торговых команд.
  PAPER остаётся OFF. Сохранённые scheduler heartbeat events растут штатно; OPEN/
  CLOSE история и финансовый state проверяются отдельно и не должны изменяться.

## Источники протоколов

- https://api-docs.render.com/reference/create-deploy
- https://render.com/docs/deploys
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/

Workflow .yml записан в JSON-подмножестве YAML: его разбирает GitHub Actions, а
syntax/actual job expressions и встроенный Bash проверяются без новой YAML
runtime-зависимости. Все actions закреплены полными commit SHA; Python и pip
зависимости — существующими .python-version и ci/requirements.lock.

## WORKER_SETTINGS_CHANGED и оставшаяся staged Version

См. [безопасную диагностику](ACTIVE43_WORKER_SETTINGS_EVIDENCE.md). Новый manual
operation `inspect_worker` делает только GET, доступен при deploy enabled=false и
не требует удаления/активации staged версии. Обычный deploy при таком состоянии
собирает field-level evidence и по-прежнему BLOCKED до review. Никакой автоматической
коррекции настроек или слепого возобновления POST не предусмотрено.


Выбор точного main CI, безопасный auto-discovery и разбор неверного ID из Issue #36:
[ACTIVE43_CI_ISSUE36.md](ACTIVE43_CI_ISSUE36.md). Пустой input не означает пропуск CI.

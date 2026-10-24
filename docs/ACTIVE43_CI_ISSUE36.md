# Issue #36: точная причина и исправление выбора CI

## Подтверждённая причина

Исходный inspection run:
https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40125643421

В его логе фактически указано **RELEASE_CI_ID: 40120701255**, а не 40124624433.
Checkout был `02366e96d119786d190c622acd30eaf5d05a518b`.

| Показатель | Фактически переданный CI | Подходящий CI |
|---|---|---|
| Run ID | 40120701255 | 40124624433 |
| Head SHA | af325769663b0d6593b64eb844e56558957e6647 | 02366e96d119786d190c622acd30eaf5d05a518b |
| Branch/event | main/push | main/push |
| Workflow ID | 394467730 | 394467730 |
| Status/conclusion | completed/success | completed/success |

В compound condition старого контроллера отвергнуто **head_sha == checkout SHA**.
Это корректная защита от CI другого коммита, а не отказ успешному CI текущего main.
Фраза Issue о переданном 40124624433 не соответствует фактическому env лога.

Проверка обоих контроллеров только через GitHub GET metadata (без Render/CF/БД):
старый и новый отвергают 40120701255; старый и новый принимают 40124624433 для
02366e9, включая job/steps/environment checks. Новый auto-discovery также нашёл
40124624433. Это не запуск production workflow и не проверка Cloudflare.

Источники CI:
- https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40120701255
- https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40124624433

Санитизированная offline fixture `tests/fixtures/active43_issue36_ci.json` содержит
только нужные публичные поля реальных run/workflow/job/steps. Secrets, headers,
профили пользователей и полный GitHub API response туда не включены.

## Что исправлено

1. Для manual deploy/rollback/inspect поле `ci_run_id` можно оставить пустым.
   Контроллер ищет completed/success **push/main** run нужного workflow **только
   для текущего checkout SHA**, а затем заново читает selected run и проверяет
   полную identity, завершённый regression job и оба regression/report steps.
2. Неверный **явно указанный ID не подменяется молча**: BLOCKED с точными
   `ci_validation.failed_checks`, ожидаемым/фактическим SHA и workflow ID.
   Чужой repo, event/branch/workflow/SHA, skipped/incomplete jobs/steps и отсутствие
   отчётов остаются блокерами. Repository/job неизвестные значения не отражаются
   в логи; выводятся фиксированные enum/boolean или безопасные SHA/ID.
3. Проверяются trusted workflow path/state, response run ID, completed job/step
   статусы. Top-level success не заменяет job/report integrity. Существующий
   CI `check_results.py` продолжает запрещать skipped/failed/пустые тестовые отчёты.
4. При отсутствии подходящего run — EXACT_MAIN_CI_NOT_FOUND. При неполной выборке
   (более 100 runs на один SHA) — CI_DISCOVERY_INCOMPLETE, а не выбор другой истории.
   workflow_run по-прежнему передаёт собственный CI ID; discovery нужен для ручного
   пустого поля. Никакого fallback на старый Render SHA или CI предка main.

Официальный GitHub API поддерживает фильтры head_sha/branch/event/status:
https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow

## Почему inspect_worker сохраняет тот же CI gate

Он читает production configuration с привилегированным Cloudflare token из
защищённого environment. Требование trusted/tested main code сохранено осознанно,
хотя его Remote принудительно GET-only. Оно не заменяется простым успешным run
любого коммита и не отключается ради read-only. Environment main-only и owner
разрешения не меняются. Флаг автоматического deploy может оставаться false;
inspect_worker продолжает работать без любых POST.

## Проверка после отдельно разрешённого merge

1. Дождаться успешного **нового push/main CI**. После merge SHA изменится: старые
   исторические ID из таблицы выше не копировать для нового main.
2. Production Deployment → Run workflow → main → `inspect_worker`.
   **ci_run_id оставить пустым**. При необходимости указать существующую staged
   UUID `8804fedf-fc51-4aab-a801-b4ca66cc0bda`; пустая UUID означает чтение latest.
3. В Summary/artifact проверить `ci_validation.status=PASS`, resolved `ci_run_id`,
   все checks=true и затем `worker_diagnostics`. Итог WORKER_INSPECTED_NO_DEPLOYMENT
   не означает DEPLOY_VERIFIED и не разрешает автоматически активировать stage.

Новые Secrets, env, SQL, services, Worker upload/activation, Render deploy и
переключение PAPER не нужны. Проблема WORKER_SETTINGS_CHANGED остаётся отдельной
диагностикой: этот PR лишь позволяет пройти правильный exact-main CI gate.

## Тесты и review

Реальные публичные fixtures: старый ID однозначно даёт только run_head_sha=false;
правильный ID проходит все guards; пустой input обнаруживает только exact SHA.
Adversarial fixtures: чужие SHA/branch/event/repo/workflow, неправильный run ID,
missing/skipped/incomplete job/report steps, неверный descriptor, stale main и
неподходящие discovery candidates. Все negative cases остаются BLOCKED до любых
Render/Cloudflare вызовов. Полные Python/Node тесты и exact-head Regression CI
выполняются отдельно; production/staged configuration этим PR не изменяется.

# WORKER_SETTINGS_CHANGED: подтверждённые факты и безопасная диагностика

## Что установлено

Изучены main `af325769663b0d6593b64eb844e56558957e6647`, workflow и controller.
Production run #5: https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40122405165

В 2026-10-24 18:49:07 UTC controller записал:

- Render SHA `af325769663b0d6593b64eb844e56558957e6647`;
- предыдущую активную Worker Version `1476440e-4b76-46e2-a5af-433643890d1d`;
- загруженную staged Version `8804fedf-fc51-4aab-a801-b4ca66cc0bda`;
- только mutation `WORKER_VERSION_UPLOAD_REQUESTED`;
- затем `WORKER_SETTINGS_CHANGED`.

Код выбрасывает эту ошибку в post-upload invariant: весь результат нового
`GET /settings` после `profile()` не равен сохранённому pre-upload профилю.
`profile()` лишь сортирует bindings по имени; другие поля, включая вложенные
структуры/необязательные поля, сравниваются полностью. Ошибка произошла до
`WORKER_ACTIVATION_REQUESTED` и до сравнения candidate resources.

**Конкретное поле production не доказано.** В старом отчёте нет обоих settings
снимков и нет путей различий. Нет авторизованного доступа к Cloudflare/Render;
configured Secrets доступны только production Actions environment. Текущее
активное состояние Cloudflare по старому checkpoint не объявляется подтверждённым.
Из сообщения нельзя решить, изменились ли реальные bindings/runtime, добавились
ли метаданные или отличилась форма ответа. Не названо предположительное поле и
не добавлен список полей для слепого игнорирования.

## Что меняет PR

- Любая неравная пара settings/schedules/subdomain/staged resources теперь
  записывает component, code и **точные безопасные schema paths** различий:
  например `$.observability.enabled` или `$.bindings[2].type`. Только типы и факт
  изменения/отсутствия; никаких значений, размеров значений или их fingerprints.
- Неизвестные ключи и имена bindings не отражаются в логи: вместо потенциально
  секретного key — `unknown_field_N`, вместо имени — индекс элемента.
- Ничего не исключено из защищённого сравнения. Нормализация binding order остаётся
  прежней. ISO-date, отсутствующее поле/null/пустое значение, flags/list order,
  limits, observability и неизвестные поля не объявляются эквивалентными без
  доказательств. Реальное изменение всё ещё BLOCKED. Одна независимая ошибка
  Python equality исправлена: JSON boolean `true` больше не равен числу `1`;
  это воспроизводимый дефект сравнения, **не доказанная причина run #5**.
- При уже существующей staged версии обычный deploy выполняет только чтения,
  добавляет диагностику и сохраняет `UNDEPLOYED_WORKER_VERSION_REQUIRES_REVIEW`.
  Никакого нового Render deploy/Worker upload/activation или слепого POST.
- Новый `inspect_worker` через тот же workflow — принудительно GET-only Remote.
  Даже программная попытка вызвать разрешённый mutator отвергается до сети.
  Режим работает при deploy enabled=false, но требует main, прошедший CI и
  защищённый main-only environment. Существующие Secrets/IDs переиспользуются.

## Как получить недостающие данные после разрешённого merge

Ничего из этого не выполнялось разработчиком в production.

1. Открыть https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/production-deploy.yml
   → Run workflow → branch `main` → operation `inspect_worker`.
2. `ci_run_id` оставить пустым: auto-discovery найдёт успешный **push/main** CI
   точного SHA после merge. Явно заданный старый ID по-прежнему BLOCKED (Issue #36).
   `inspect_worker_version`: `8804fedf-fc51-4aab-a801-b4ca66cc0bda` (если она всё
   ещё существует). Пустое поле означает latest. Не включать PAPER и не менять
   deployment enable flag ради чтения. При required reviewer подтвердить только
   этот GET-only запуск.
3. Скачать `deployment-report.json` или открыть Summary:
   `worker_diagnostics` содержит актуальные active/latest/inspected UUID,
   `active_staged_resources`, `current_vs_active_*`, `current_vs_staged_*`,
   `inspection_settings_stable`, совпадение Cron. Все различия — без значений.

`WORKER_INSPECTED_NO_DEPLOYMENT` означает успешный сбор, не DEPLOY_VERIFIED и не
разрешение активировать candidate. `safe_to_resume=false` намеренно сохранён.
При активной автоматизации после merge обычный deploy сам обнаружит оставшуюся
staged версию, соберёт такие данные и остановится **до production POST**. Отдельный
ручной inspect полезен при выключенном флаге или для указанной конкретной UUID.

Текущие GET не восстанавливают утраченный pre-upload settings snapshot старого
run. Даже если active/staged resources равны, это не доказывает историческую
причину всего `GET/settings` mismatch. `root_cause_confirmed=false` не меняется
на true по догадке. Если данных immutable versions недостаточно, нужен прежний
безопасный field-diff baseline из лога либо отдельно разрешённый контролируемый
upload после review staged-состояния; не повторять POST ради диагностики сейчас.

## Повторный запуск и оставшаяся staged Version

**Не нужно удалять, активировать или откатывать 8804… для установки этой правки.**
Сначала выполнить только inspection. Сам PR не изменяет ни эту, ни другую версию.
Обычный deploy после merge безопасно повторить в смысле отсутствия слепых POST,
но он **не обязан завершиться**: pending staged Version продолжает блокировать
публикацию. Resume/re-upload/activation не автоматизированы без доказательства
одинакового защищённого профиля и отдельного разрешения владельца.

## Граница проверки secrets

Удаление/переименование/type/inventory changes secret bindings, изменения
возвращаемых opaque fields, обычных binding values/resource IDs, runtime и Cron
по-прежнему отклоняются. Тесты проверяют эти случаи и отсутствие утечки значений.
Если Cloudflare возвращает только одинаковые `name`/`type`, **ротация содержимого
secret с тем же именем не наблюдаема** через эти GET. Нельзя честно утверждать,
что её значение равно старому: `secret_value_equality_verified=false`.
Для такой проверки нужны платформенный audit/контроль отсутствия ротаций,
а не вывод самого секрета. Новый код не читает и не меняет secret values.

## Проверки

Regression cases: разные settings поля/формы и реальные binding/secret inventory
изменения; флаги/даты/null/missing и неизвестные поля; boolean/number; Cron и
subdomain; post-upload mismatch без activation; безопасное повторение со staged
версией без любых POST; GET-only inspection с выключенной автоматизацией;
редактирование неизвестных ключей/значений и ограничения размера диагностики.
Полные Python/Node regression и exact-head CI запускаются отдельно.
Стратегии, риск, Worker код, PAPER, Aura4.2/Practice, SQL и Supabase не меняются.

Issue #38 добавляет только доказанную missing/empty flags нормализацию и явные
EMPTY/NONEMPTY states, сохраняя raw evidence и блокировку staged activation.
См. [разбор и процедура](ACTIVE43_COMPATIBILITY_FLAGS_ISSUE38.md). Старый отчёт с
типом array не доказывает, что flags были пусты; исторический root cause остаётся
неподтверждённым без утраченного baseline.

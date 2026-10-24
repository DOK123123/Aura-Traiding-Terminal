# Issue #38: compatibility_flags и безопасная staged-проверка

## Подтверждённая диагностика

GET-only run: https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40129231336
Main SHA этого чтения: 78a0b894520700d0b53221aa2cf3e4bbe1ebd238.
Active: 1476440e-4b76-46e2-a5af-433643890d1d.
Staged: 8804fedf-fc51-4aab-a801-b4ca66cc0bda.

В отчёте active/staged bindings и полный script_runtime равны. Между settings и
runtime обеих версий есть только compatibility_flags missing -> array. Cron
совпадает; два текущих settings чтения стабильны. Но **array не означает []**:
прежний redacted отчёт не записывал пустоту массива. Строго доказать, что именно
этот production массив пуст и что это была единственная причина старого upload
failure, по доступным данным нельзя. Pre-upload settings первого run утрачены.

## Прослеженная цепочка и воспроизводимый дефект

1. Versions GET `resources.script_runtime.compatibility_flags` — optional field;
   оно отсутствует в показанных immutable версиях.
2. Settings GET `compatibility_flags` — optional array, в run присутствует.
3. Существующий upload_metadata всегда посылал
   `settings.get('compatibility_flags', [])`: отсутствие материализуется как [].
4. Старый profile лишь сортировал bindings, поэтому baseline без ключа и ответ
   с `compatibility_flags: []` считались разными. Это воспроизводится fixture
   из payload materialization без каких-либо реальных запросов на запись.

Таким образом **класс false mismatch доказан в коде**, но воспроизведение — не
выдуманная запись двух исторических production settings снимков. Если в реальном
settings NONEMPTY, правило below не объявит его эквивалентным отсутствию.

## Почему missing и [] эквивалентны в узком контексте

Cloudflare описывает compatibility_flags как список явных overrides поверх
compatibility_date. Workers SDK/Wrangler задаёт default [] для optional flags.
При одной и той же валидной fixed compatibility date missing/[] означают **нет
явных overrides**, а не отсутствие всех возможностей runtime. Date-enabled
defaults сохраняются; даты или сам runtime не изменяются этим PR.

Первичные источники:
- https://developers.cloudflare.com/workers/configuration/compatibility-flags/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/
- pinned environment.ts, @default []:
  https://github.com/cloudflare/workers-sdk/blob/ac79539606c583de8b7cb52c1c4857855d385961/packages/workers-utils/src/config/environment.ts#L587
- pinned config.ts, compatibility_flags: []:
  https://github.com/cloudflare/workers-sdk/blob/ac79539606c583de8b7cb52c1c4857855d385961/packages/workers-utils/src/config/config.ts#L363
- pinned validation.ts, inheritable optional flags defaults []:
  https://github.com/cloudflare/workers-sdk/blob/ac79539606c583de8b7cb52c1c4857855d385961/packages/workers-utils/src/config/validation.ts#L1570

Это основание только для отсутствующего **этого поля** -> [] в копии runtime с
проверенной календарной YYYY-MM-DD date. Нет нормализации дат, flags порядка,
других отсутствующих/default значений, unknown fields или непустых overrides.

## Изменение кода

- Один runtime_profile для settings, immutable version resources и comparisons.
  Работает с deep copy: production bindings/flags/date не записываются и не меняются.
- missing -> []; EMPTY сохраняется. NONEMPTY сохраняется буквально; удаление,
  добавление, перестановка или изменение flags остаются mismatch. Null, строка,
  неверный тип элементов и отсутствующая/невалидная date — BLOCKED до POST.
- upload payload семантически прежний: отсутствие и раньше посылалось как [].
  Теперь guard согласован с этой семантикой, а invalid values не уходят на upload.
- Все прочие runtime/settings/bindings/secret inventory/subdomain/Cron guards
  сохранены, как и запрет менять routes. Boolean/number проверяется типобезопасно.
- Inspector оставляет raw comparisons и добавляет MISSING/EMPTY/NONEMPTY/INVALID
  states, normalized_runtime_comparisons, flags_representation_equivalent и
  known_protected_config_matches. Flag names/values и секреты не логируются.
- Никакого автоматического resume, нового operation activation или POST в
  inspection. Существующий staged guard по-прежнему блокирует обычный deploy.
  `safe_to_resume=false`, `activation_authorized=false` сохранены даже при match.

## Что известно о staged code

Worker source в repo на af325769663b0d6593b64eb844e56558957e6647 и на 78a0b89 совпал
побайтово: SHA256 d2dbbb35f89acc693072c9d54161e14d109a37880e65f9a4d04dffe5c61dab33.
Это **не независимое чтение кода 8804… из Cloudflare**. Для решения об активации
требуется review provenance именно staged UUID и оригинального upload report.
Содержимое same-name secrets также не доказывается GET; не ротировать их ради
устранения mismatch. Публичный source digest не является fingerprint секретов.

## Точные действия владельца после отдельно разрешённого merge

Ничего в production этим PR не выполнялось. Не удалять и не активировать 8804…
для установки этой правки и не делать новый upload ради диагностики.

1. Дождаться нового успешного main CI. В
   https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/production-deploy.yml
   создать **новый Run workflow**: main, inspect_worker, CI ID пустой, inspected
   version 8804fedf-fc51-4aab-a801-b4ca66cc0bda. Deploy flag можно оставить false.
2. В Summary/artifact проверить compatibility_flags_states. Только фактические
   MISSING/EMPTY при одинаковой проверенной date и equal normalized comparisons
   дают flags_representation_equivalent=true. При NONEMPTY vs MISSING, INVALID,
   неверной date, runtime/binding/Cron drift — остановиться без исправления flags.
3. known_protected_config_matches=true означает совпадение **известных прочитанных
   полей**, не разрешение на публикацию. До активации отдельно зафиксировать
   текущий settings baseline, подтвердить источник staged code и отсутствие
   ротации secrets, повторно проверить OFF/empty account и получить отдельное
   разрешение владельца на activation/deploy. Этот PR такого действия не делает.

Исторический потерянный baseline ограничивает **объяснение прошлого сбоя**; для
отдельно разрешённой будущей активации нужен новый проверенный current baseline,
а не искусственно восстановленная старая конфигурация. Ограничения исторического
вывода и текущие activation blockers в отчёте разделены.

Обычный повторный deploy с имеющимся inactive stage безопасно BLOCKED до POST;
сам по себе merge не заставит его продолжить публикацию. При уже включённом
автоматическом workflow staged-preflight только соберёт расширенную диагностику.
Новый staged upload/activation, rollback, env, SQL, PAPER ON не выполняются.

## Проверки

Tests воспроизводят old failure class, no-op empty materialization в settings и
version resources, обе missing/empty стороны, invalid/null/date cases, реальные
непустые runtime изменения, unchanged nonempty flags, строгую семантику других
полей, redaction и staged guard без POST даже при normalized match. Существующие
регрессии bindings/secret metadata/Cron/routes и CI/main/GET-only guards остаются.
Полные Python/Node тесты и exact-head CI проверяются отдельно. Локальные fixtures
не выдаются за проверенный production upload или разрешение активировать Worker.

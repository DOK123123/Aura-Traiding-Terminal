# AURA RESEARCH LAB — INTEGRATION AUDIT

Дата: 2026-10-16 UTC. Проверен main `c50fd0bb2402bd261089142c96d4e9981f4594ab`, PR3–7 на точных SHA ниже.

**NOT READY FOR INTEGRATION / DEPLOY OF PR #7.** CLI и короткие HTTP-фикстуры ранее не выявили отказ сохранения одного из четырёх полноразмерных результатов. Этот аудит воспроизводит проблему. До исправлений и проверки инфраструктуры #7 следует оставить Draft.

Merge, deploy, изменение production, запросы к production Supabase и реальные LLM-вызовы **не выполнялись**. В этой ветке добавлены только аудит, тесты, локальный benchmark и исправление инструкции упаковки; runtime-код лаборатории и торговли не менялся. Это не исправляющий execution PR и не разрешение на интеграцию.

## 1. Фактическая цепочка GitHub

| PR | Head SHA | Base | Состояние |
|---|---|---|---|
| #3 | `f0ae5b04dca0cea5c0c4c2f39dafbc62a3df2446` | `main` | Draft, open, merged=false; mergeable=True |
| #4 | `7f5516a15944414d0b70491f68234e1f84a95a46` | `codex/aura43-adaptive-lab` | Draft, open, merged=false; mergeable=True |
| #5 | `758ffb48a14ab1ad852b7bf431c29c0262e9cc9d` | `codex/aura43-frequency-research` | Draft, open, merged=false; mergeable=True |
| #6 | `d7ae130f863cab243600930bd54dc50e927ee04a` | `main` | Draft, open, merged=false; mergeable=True |
| #7 | `4415383b680d404f8eb9f25df11a6e346ad76bd6` | `codex/strategy-lab-v2` | Draft, open, merged=false; mergeable=True |

Зависимости: **main → #3 → #4 → #5 → #7**. **#6 → main независимо**. PR1/2 уже находятся в main. Содержимое Draft не считается содержимым main. GitHub `mergeable=true` означает отсутствие текущего текстового конфликта, а не безопасность выпуска. GitHub может возвращать SHA тестового merge-коммита даже при `merged=false`; этот SHA не принят за выполненный merge.

Проверено по Git ancestry: каждый исследовательский parent является предком следующего head. С main после общего основания новых изменений нет. Пять добавляемых #6 файлов не пересекаются ни с одним файлом совокупных изменений #3–#7. Для теста создан detached checkout #7, в который скопированы только эти пять новых файлов #6 и новый интеграционный тест. Никакой merge/cherry-pick/перемещение main/ref/merge commit не выполнялись. Эта файловая копия использовалась исключительно как тестовый стенд.

Конфликтов на проверенных SHA не обнаружено. После любого изменения main, rebase/squash или исправления родителей вывод надо проверить заново. Новые commit SHA сами по себе не ломают артефакты, но изменение байтов файлов из software manifests ломает их строгую валидацию: нельзя просто переписать hashes и объявить старые финансовые результаты новыми.

Переиспользование подтверждено: исходный Lab предоставляет owner/CSRF, импорт/агрегацию/индикаторы; #3–#5 предоставляют native replay, v2 risk adapter и независимые оракулы; Research Lab использует существующий Candidate C и DONCHIAN. Нового торгового движка, provider switch, production registry или расписания нет. Отдельные SQLite Research и Legacy Lab — намеренная изоляция, не случайное дублирование портфеля.

Существующие функции и request schema в `app/lab/api.py` сравнены AST с main и полностью совпадают; родительские PR добавляют только отдельные saved-report GET routes. Новый #7 добавляет `/api/research` и два include/import в app.main, а не заменяет существующие API. Повторных method/path-регистраций нет. Старые Lab endpoints и три пакета adaptive43/profiles43/v2 успешно прочитаны в том же приложении, где подключён Research Lab.

## 2. Обнаруженные проблемы и предлагаемые исправления

### F1 — HIGH, блокирует #7: сохранение Volatility Breakout

`app/research/storage.py:76` сериализует весь результат одним JSON и ограничивает его `MAX_RAW=33,554,432` байт (32MiB). Семь полноразмерных прогонов Volatility Breakout дают **36,461,574 байт**. `Store.finish` воспроизводимо бросает `RESULT_LIMIT`. `Service.run` ловит исключение и сохраняет ERROR/RESEARCH_FAILED_NO_PROMOTION вместо результата; HTTP возвращает RESEARCH_RUN_FAILED. Предварительно опубликованный CLI-артефакт читается в summary, но повторный полный запуск через UI не сохраняется. CLI не использует этот лимит Store — причина расхождения тестовых путей.

| Артефакт | Raw bytes | Compressed bytes | Вмещается в текущий Store |
|---|---:|---:|---|
| MEAN_REVERSION | 21124121 | 599912 | да |
| LIQUIDITY_SWEEP | 27608368 | 836896 | да |
| REGIME_SWITCHING | 31958803 | 1042433 | да |
| VOLATILITY_BREAKOUT | 36461574 | 1039976 | НЕТ |

Предлагаемое исправление: использовать существующий PR5 pattern разделения manifest/decision logs. После аудита каждого run сохранять полный журнал в отдельный ограниченный gzip/JSONL, с SHA256 и уникальным путём experiment/attempt/split/scale; в SQLite держать компактный manifest, метрики, сделки и ссылки. Чтение журналов — owner-only, ограниченное и постраничное. В текущем PR5 helper имена не включают scale, поэтому для повторного использования нужны отдельные каталоги scale, иначе чувствительности перезапишут друг друга. Публиковать manifest атомарно только после целостного сохранения файлов. Проверить crash/retry/orphan recovery и сопоставить финансовые результаты со всеми28 исходными runs.

Не повышать лимит вслепую: это усугубит F2. В рамках аудита код хранения не менялся. Добавлен strict xfail-тест ожидаемого успешного сохранения: он фиксирует известный дефект, не объявляет его исправленным. После исправления нужно снять xfail и потребовать PASS.

### F2 — HIGH для общего production-инстанса: RAM, CPU и event loop

`Service.run:44` использует asyncio.to_thread в том же процессе, а не изолированный процесс/сервис. В `experiment.execute:36` 180-секундный бюджет проверяется только между run: это не жёсткий timeout/лимит памяти одного replay, аудита, JSON-сериализации или compression. Полный export дополнительно сериализуется через JSONResponse в event loop.

Реальный REGIME_SWITCHING прогнан через настоящие ручные HTTP endpoints на временном SQLite, без production lifespan. Его полный checksum **совпадает** с ранее опубликованным результатом (все семь split/sensitivity runs). Профиль НЕ включает декодирование эталонного артефакта: оно выполнено после снятия метрик, чтобы не завысить оценку ресурсов дополнительной копией reference report. ASGI-клиент находится в том же процессе; измерения включают его небольшие накладные расходы и буфер полного ответа. Это локальная оценка, не Render benchmark и не гарантия worst case.

- Среда: Linux cgroup2 CPU /8GiB, Python3.12.14; production lifespan, сетевые market fetch и LLM отсутствовали.
- Baseline import RSS: **54.5 MiB**. Пик RSS до загрузки reference: **428.2 MiB**, прирост около **373.7 MiB**.
- Run + export: **15.38s wall**, **15.51s CPU**.
- Health probes: 241, max latency **0.656s**; max event-loop probe gap **0.718s**. Это не измерение реального scheduler latency.
- Полный export: **31,963,085 bytes**, **0.766s**. SQLite одного исследования: **1,073,152 bytes**.

На общем512MB-инстансе такой пик вместе с реальными market/pattern caches может вызвать OOM или задержки Auto42. Текущий тариф, фактическая RAM/CPU, диск и нагрузка Render недоступны в этой сессии; достаточность текущей инфраструктуры **НЕ ПОДТВЕРЖДЕНА**. Изменения кода стратегии нет, но shared resource contention может повлиять на доступность торгового scheduler — нельзя обещать обратное по одному passing test.

До deploy: вынести вычисление в контролируемый отдельный процесс/исследовательский сервис с жёсткими лимитами wall time/RSS и одним ручным заданием; уменьшить монолитные payloads по F1 и проверить mixed-load. Даже отдельный process на том же маленьком контейнере не отменяет общего memory/cgroup лимита. Для первого отдельного staging-профиля разумная начальная конфигурация —1vCPU/1GiB RAM и постоянный диск не менее1GiB, но это рекомендация для замера, не доказанная достаточность и не команда покупать/менять тариф. Для совместного production sizing нужна фактическая baseline Aura плюс measured headroom. Worker архитектура автоматически не внедрялась.

### F3 — MEDIUM: ошибка типа сохранённого отчёта даёт HTTP500

`Store.get:118` считает, что декодированный JSON — dict. На корректном gzip с JSON `[]` вызывается list.pop('checksum',None), возникает TypeError, который не обработан в API.respond. Получается обычный HTTP500 вместо структурированного RESEARCH_INTEGRITY/no-store503. Повреждённый gzip и sqlite errors уже корректно дают503. Этот случай воспроизведён отдельным strict xfail; доступа без owner или утечки ключей он не даёт.

Предлагается явно валидировать тип и обязательные поля report/config/manifest до использования, выдавая LabError(RESEARCH_INTEGRITY). Не маскировать любые исключения бесконечным catch/retry. Runtime исправление в аудит не включено.

### F4 — MEDIUM: устаревшие инструкции упаковки

Старый docs/DEPLOYMENT.md называл scripts/docs необязательными и советовал не переносить JSON-отчёты. Но #7 импортирует scripts.research_lab_v2 из app.main через router/service/experiment; при старте читает docs/STRATEGY_LAB_V2_PROTOCOL.json и transitive protocol dependencies. Отсутствие обязательного протокола воспроизведённо ломает импорт app.main целиком — может не запуститься и Aura4.2.

**Исправлено только в документации:** сохранить полный checkout (app/static/research/scripts/docs, фиксированные протоколы/артефакты/data/logs). Runtime и финансовые manifests не менялись. Этот документационный fix входит в аудит и должен быть учтён перед выпуском. Обычный полный Render Git checkout содержит файлы; проблема возникает при slim packaging/удалении docs/scripts.

### F5 — инфраструктурное обязательное условие: постоянный Research ledger

Текущий путь жёстко задан: `<repo>/.data/ai-research/ai-research-v1.sqlite3`. Это отдельный SQLite с queue/events/llm_calls, не trading tables и не Supabase. Вновь открытый тот же файл восстанавливает completed result, события, pending QUEUED, RUNNING и зарезервированный LLM бюджет в **новом интерпретаторе**. Новая/пустая файловая система не содержит прежней истории. Ни тест нового процесса, ни флаг PERSISTENT_STORAGE_CONFIRMED не доказывает сохранность диска на настоящем Render.

Официальные Render Docs (прочитаны в этом аудите): https://render.com/docs/disks и https://render.com/docs/free — без persistent disk изменения локальных файлов теряются при redeploy/restart; Free web service не поддерживает persistent disk. Не объявляется, что production сейчас использует Free: реальный план неизвестен.

Постоянный диск должен покрывать **именно этот каталог**, например `/opt/render/project/src/.data/ai-research` при стандартном checkout, а не только `.cache`. Symlink-research path отвергается защитой, поэтому нельзя решать это симлинком или подменой PAPER_DB_PATH/LAB_DB_PATH. Если уже существующий disk/mount не покрывает путь, нужен отдельный изолированный storage/service дизайн; не переносить production ledger и не менять его mount ради аудита. Новая research база/схема/RPC Supabase для текущей версии не нужны. В будущем отдельный research backend допустим только отдельным reviewed change, без торговых таблиц.

Опубликованные frozen CLI-отчёты из Git сохраняются после redeploy при полном checkout: это отдельные assets, не динамическая SQLite-история. Новые задания, результаты ручных циклов, события и бюджетные резервы требуют сохранения SQLite.

SQLite бюджет действует за время жизни сохранённого файла; потеря файла сбрасывает учёт расходов. LLM оставлен выключенным. Он не нужен для очереди/backtest/аудита. Для работы без LLM новых переменных не требуется: используется существующий owner password; `AURA_RESEARCH_LLM_ENABLED=false` можно явно установить в будущем staging. Не добавлять ключи/платного провайдера для интеграционного теста. Любое будущее включение требует достоверного persistent ledger, корректных цен, лимитов и отдельной ручной проверки провайдера.

## 3. Работа компонентов и изоляция

| Компонент | Проверено | Ограничение |
|---|---|---|
| Researcher | Фиксированные четыре гипотезы, шесть проверяемых источников, честный AI_NOT_CONFIGURED | Без API это curated protocols, не имитация трёх LLM |
| Backtester | Существующий kernel, закрытые15m/1h/4h,60/20/20, fees/slip, frozen config | Полный Volatility report не сохраняется через UI (F1) |
| Auditor | Независимые Fraction/Decimal raw-fill/PnL/DD checks, causal-prefix/future mutation tests | Год уже изучен, свежей независимой выборки нет, promotion отключён |
| Queue | Owner manual enqueue/run/retry, атомарный claim, attempt fencing, no startup auto-run | После crash RUNNING сохраняется; explicit recovery после10min, затем ручной retry/run |
| Registry | Allowlist гипотез, клиент/LLM не меняют параметры | Новую LLM-идею нельзя автоматически превратить в исполняемый код |
| History | Новый процесс читает тот же SQLite, checksum и metadata сохраняются | Потеря ephemeral filesystem теряет новые исследования |
| UI |20 Node suites,12 поведенческих checks страницы, textContent, отсутствие auto requests/LLM/research | Нет настоящего browser/Render end-to-end теста; полный export тяжёлый |
| LLM adapters | Fixed OpenAI/Mistral HTTPS/no redirects, env-only keys, mock errors/usage/caps/reservations | Реальные providers не вызывались; paid connectivity NOT TESTED |

Все research endpoints требуют owner. Все мутации требуют также Lab CSRF header и same-origin; cross-site отклоняется. Ненастроенный LLM не тратит бюджет. Research/Lab IDs не читаются через чужое хранилище. Проверены совместные HTTP-чтения старого Lab и новых frozen reports, сохранение research queue, owner login, API errors и no-store. Подключённый sentinel trading state бросает исключение при обращении; конструкции Auto42 Service, Paper Service и SupabaseStore запрещены в проверке. Запросы лабораторий проходят без них, hash отдельного sentinel trading файла не меняется.

Research использует pure open_virtual для симуляции исторических RAM-позиций. Это не запрос открытия production Paper и не реальный биржевой order. У модуля нет ссылки на controller/store действующего счёта, scheduler, SQL/RPC или функции deploy. Исследования не записываются в существующие торговые таблицы. Отдельный #6 harness запускается только в тестовой копии и также не устанавливает LIVE VERIFIED.

Защищённые пути app/automated, app/paper, app/forward, app/intelligence, providers, scheduler/SQL/dependencies не изменены ни #7, ни этим аудитом по сравнению с main. Единственная runtime-интеграция #7 — import/include нового router и ссылка в HTML; startup становится зависим от перечисленных assets. У текущего аудит-PR runtime diff против #7 пустой.

## 4. Ресурсы и сохранность

- Дополнительный постоянно работающий LLM/AI процесс не создаётся. В покое — новый router/imports, metadata, малый SQLite; dataset cache загружается лишь при ручном backtest и остаётся в памяти процесса.
- Один измеренный full cycle временно добавляет около374MiB к импортированному baseline; CPU около15.5core-seconds. Точные цифры в AI_RESEARCH_INTEGRATION_RESOURCES.json.
- #7 добавляет около3.50MiB tracked files к #5; весь набор #3–#7 добавляет около15.21MiB к main. Это сумма Git blob sizes, не полный размер build/image, pip packages, Git objects или runtime RAM.
- SQLite измеренного исследования около1.02MiB; четыре gzip CLI artifacts около3.36MiB, но распакованные payloads21–36MB каждый. Политика32jobs/8MiB compressed result/128MiB pre-access DB check не заменяет план хранения/backup или hard filesystem quota. Для роста нужны retention/export и проверка лимита до write; просто увеличивать caps нельзя.
- No Supabase table/schema migration. Persistent isolated SQLite достаточен только для одного экземпляра/его filesystem; не распределённая очередь и не единый бюджет нескольких независимых Render hosts.

## 5. План будущей интеграции — НЕ выполнен

Перед любым будущим merge получить отдельное разрешение владельца и проверить Render Auto-Deploy: merge в main может сам запустить deploy. В этом аудите настройки Render не менялись. Не применять этот список как разрешение merge/deploy.

| Этап | Что объединять после разрешения | Проверки | Риск и откат |
|---|---|---|---|
|0|Ничего: исправить F1/F3, выбрать resource/persistence architecture, staging acceptance|Оба strict xfail перевести в обязательный PASS; полноразмерные4hypotheses HTTP save/get/export/restart; financial equivalence всех28runs; mixed-load; actual disk survival|До выполнения #7 остаётся Draft; никаких production настроек|
|1|#6 необязательно, независимо от исследовательской цепочки; можно раньше #3|Его10tests,12scenarios технического CLI, полный combined suite; никакого runtime import harness|Пять новых тестовых/документальных файлов. Откат отдельного commit не затрагивает портфель|
|2|#3 в main|Полный Python/Node, adaptive43 owner reports, source/code hashes, frozen native comparison|Новый read-only research UI. При отмене удалить child dependencies сначала; исходные portfolio данные не откатывать|
|3|#4 после #3|Retarget base на main, чистый incremental diff, profiles43 artifacts/evidence + полная регрессия|Не скопировать повторно изменения #3; rollback до выпуска #5 или сначала откатить детей|
|4|#5 после #4|v2 report и все44decision logs, native/ATR causal oracles, API compatibility, source hash|Native risk adapter — Lab only. Artifact hashes могут ломаться при source rewrites; rollback после удаления зависимого #7|
|5|#7 только ПОСЛЕ этапа0 и #5|Retarget/rebase, no xfails, full4HTTPcycles, same closed candles/accounting, auth/noLLM, persistent restart, CPU/RSS acceptance|Высокая shared-resource цена и storage F1 до исправления. Откат router/link/code #7, сохранить research DB/backup, не удалять budget/history|
|6|Этот audit-only PR опционально после #7/fixes|Снять strict xfail markers только после исправления и PASS; обновить отчёт фактическими SHA/результатами|Аудит не исправляет F1/F2/F3. Не считать его merge заменой исправлениям|

При сохранении ancestry обычными merge-коммитами стек проще перепроверить. При squash/rebase каждого parent явно retarget/rebase следующего child на обновлённый main, проверить только его incremental patch и финансовые manifests. Не выполнять bulk merge #3–#7 одним неконтролируемым шагом. После каждого этапа запускать full suite; deploy не является обязательной частью merge и не выполняется без отдельного разрешения.

Откат кода при проблеме — reverse dependency order: #7, затем #5, #4, #3; #6 независим. Использовать reviewed revert исходного PR/его изменений, а не reset финансовой базы. Точные commit IDs будут зависеть от ещё не выбранного merge/squash метода. Не восстанавливать торговую базу на старую дату, не сбрасывать balance/positions и не выключать scheduler. Research SQLite и consistent backup сохранить, LLM оставить off. Source rollback сам по себе не удаляет новый research каталог.

## 6. Render runbook после исправлений и отдельного разрешения

1. Проверить фактический Render service plan, RAM/CPU limits, filesystem/mount и Auto-Deploy. Сейчас они NOT_OBSERVED, а сообщения пользователя ONLINE/CONNECTED не определяют ресурсы/сохранность.
2. Поднять изолированный staging на reviewed exact SHA с полным Git checkout; build `python -m pip install -r requirements.txt`, Python3.12, start `python start_web.py`, один Uvicorn worker. Для вычислительно изолированного research-only сервиса/worker сначала нужен отдельный reviewed entrypoint: такого entrypoint в #7 нет. Не копировать production Supabase/exchange/scheduler secrets в research staging.
3. Проверить mount точного research пути на постоянный диск, свободное место, запись/SQLite locking и consistent backup. Не трогать существующие production mounts/paths. Без подтверждения persistent storage histories не считать durable; LLM off.
4. Использовать отдельный staging owner password (`aura` / password>=12). Не добавлять платный API: `AURA_RESEARCH_LLM_ENABLED=false`; остальные LLM variables не нужны. Оставить все production trading/scheduler env неизменными.
5. Проверить `/api/health`, `/`, `/static/research.html`, owner401/403, no-store, существующие Lab endpoints и saved artifacts. Никаких автоматических POST при загрузке страницы.
6. После F1/F2 fix выполнить вручную каждую из4hypotheses, проверить7runs/splits, все аудит-заключения, полное сохранение/экспорт/пагинацию/ошибки; сравнить финансы с исходными frozen артефактами. Параллельно на staging проверять health и simulated scheduler latency/resource headroom; production tick/позиции не вызывать для нагрузочного теста.
7. В staging выполнить настоящий restart/redeploy с сохранённым исследованием; подтвердить прежний UUID/config hash/checksum/events/queue и budget reservations без новых записей/авто-выполнения. Проверить прерванный RUNNING, ручной recovery/retry, stale-attempt fence. Новый процесс на той же локальной машине не заменяет эту проверку mount/redeploy.
8. Только после acceptance сформировать отдельный production change plan. До разрешённого deploy read-only зафиксировать текущий scheduler tick/storage status/позиции, затем после deploy убедиться, что сохранены исходные настройки/данные. Никаких RESET/START/искусственных сигналов ради теста. При ошибке использовать code rollback и сохранить ledgers; не делать Supabase reset.

## 7. Тесты и воспроизведение

Полный combined offline suite на detached #7 + пяти непересекающихся файлах #6 + новом audit test: **1272 passed, 2 xfailed, 1 warning,93.47s**. Оба xfail strict=True и отражают НЕИСПРАВЛЕННЫЕ F1/F3; это не полный release PASS. После исправления каждый должен пройти без xfail. На собственном audit test отдельно: **8 passed, 2 xfailed**. Все **20 Node suites PASS**, включая12 поведенческих checks Research UI. Одна существующая Starlette/AnyIO DeprecationWarning. Python3.12.14, pytest8.3.5; pinned requirements unchanged.

Реальный семипрогонный REGIME_SWITCHING повторён через HTTP на temp store; full checksum совпал. Все четыре сохранённых CLI artifacts сверены по checksums/current financial code hashes/config hashes. Остальные три годовых эксперимента заново финансово не пересчитывались в этом аудите; full-size storage failure Volatility воспроизведён на его реальном неизменённом артефакте. Ни один повтор не создаёт свежую независимую выборку.

Все project Python parsed/app.main import/добавленный benchmark syntax и diff whitespace/credential review проверены; runtime diff against #7 пустой. Optional ruff/mypy/bandit/coverage, actual Render restart/plan inspection и paid LLM connectivity NOT RUN. Code/security review выполнены отдельными проходами; выявленные high/medium findings остаются blockers, а не замалчиваются passing regression. Документация и тесты их фиксируют; код финансов/транспортов/сервисов не менялся.

Новые проверки: отдельный интерпретатор восстанавливает completed/queued/running/history/budget; новая ephemeral filesystem не хранит прежние записи; совместные существующие и новые HTTP routes/namespace IDs; запрет доступа к trading services/store/network; auth/CSRF на каждом endpoint; sanitized sqlite/gzip errors; AST-совместимость исходных Lab routes/schema; required runtime protocol import failure; full artifact fit inventory; два явных strict xfail воспроизводимых дефекта. Они не скрыты как PASS.

```bash
python -m pytest -q tests/test_research_integration_audit.py -rx
python -m scripts.audit_research_integration --hypothesis REGIME_SWITCHING --output /tmp/aura-research-resource-new.json
```

Output benchmark создаётся эксклюзивно, используйте новый путь. `--sandbox-poll` выбирает существующее test-runner accommodation в managed environment; runtime event-loop не меняется. Benchmark использует только temp SQLite, in-process HTTP без lifespan и блокирует сетевые connect/LLM. Реальный Render/Supabase/paid API не тестировались.

## 8. Однозначные ответы

1. **Research Lab #7 пока не готова к полной интеграции/deploy:** F1, F2 и неподтверждённая persistence обязательны к устранению/проверке; F3 тоже исправить до выпуска.
2. Найдены F1 result limit, F2 resource/timeout constraints, F3 report-type500, F4 packaging docs. Исправлена только безопасная документация F4; рискованные runtime изменения не применялись.
3. Порядок: #6 независимо/опционально, затем #3→#4→#5→#7 после fixes; этот audit не runtime dependency.
4. Финансовая логика Aura4.2 не меняется. Но общий OOM/CPU/startup asset failure способен затронуть её доступность; до resource acceptance нельзя обещать отсутствие влияния.
5. На том же сохранённом SQLite результаты восстанавливаются в новом процессе. После настоящего Render restart — только с подтверждённым persistent mount; сейчас NOT_TESTED_ON_RENDER.
6. **Да, без платного API работает**: curated hypotheses, deterministic replay/audit; честный AI_NOT_CONFIGURED, без имитации LLM.
7. Один measured case: примерно374MiB дополнительного peak RSS и15.5CPU-seconds, export32MB; это не guaranteed worst case или текущие Render limits. Нужны memory headroom и постоянный диск, предпочтительно изоляция вычисления.
8. До deploy исправить F1/F3, изолировать/ограничить compute по F2, обеспечить и испытать persistence, сохранить runtime assets, получить отдельное разрешение. Ни passing tests, ни отсутствие Git conflicts не отменяют этих условий.

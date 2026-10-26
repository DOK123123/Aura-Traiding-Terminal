# Manual Paper v1 — отчёт готовности

**Текущий вариант: Render Free + Supabase Free, 0 USD/месяц в пределах квот.** Платный Render disk не требуется. Подробности актуальной реализации и ограничений — в разделе «Бесплатный backend Supabase» ниже и [runbook](MANUAL_PAPER_LAUNCH_RUNBOOK.md). Предыдущие результаты SQLite/платного варианта сохранены как история; они не заменяют проверку последнего SHA PR #57. Код и SQL подготовлены; production deploy и применение рабочей схемы не выполнялись.

Дата: 26 октября 2026. Основа: существующий PR #57, исходный head `6a6470397129f0d72f19920f78bac2d2e3c493a1`. Проект не пересоздавался.

## Аудит и исправления

| Находка | Риск | Исправление и доказательство |
| --- | --- | --- |
| API только заглушка; нет интеграции хранения и UI | Функциональность отсутствовала | Защищённые API, lifecycle и мобильная панель подключены |
| ID запроса включал цену/время котировки | Повтор после изменения цены не восстанавливал исход операции | Fingerprint только намерения; offline replay, нормализация Decimal, lost-response тест |
| Закрытие не было привязано к позиции | Старый запрос мог закрыть следующую позицию | ID позиции в URL, fingerprint и проверке транзакции |
| Незакрываемые SQLite connections | Утечки дескрипторов/блокировок | Contextmanager с commit/rollback/finally close |
| Два отдельных SELECT проверки целостности | Конкурентная запись ошибочно выглядела как повреждение журнала | Один SQL snapshot; 30 холодных запусков, 480 конкурентных одинаковых команд, ровно 30 commits |
| Баланс восстанавливался без проверки математики | Повреждённое состояние могло продолжить работу | Проверка комиссий, gross/net, realized, баланса; отсутствие автоматического сброса |
| Котировка закрытия 15m не годится для ручного текущего входа | Учебное исполнение по известной старой цене | Отдельный серверный ticker Bitget, bid/ask, часы, 5 секунд и проверка внутри DB lock |
| Ветки ошибок server_time старого candle-адаптера не нормализовались | Неодинаковая обработка недоступности | QuoteRejected/MARKET_UNAVAILABLE без сырого ответа |
| Три исходных async-теста молча пропускались без pytest-asyncio | Ложное ощущение проверки | asyncio.run без новой зависимости; все три теперь реально исполняются |

## Фактическая проверка Manual Paper

**95 Python-тестов — PASS.** Включены:

- LONG/SHORT, независимые ожидаемые gross/net/fees, сохранение позиции/баланса/истории;
- owner auth, CSRF/Origin, strict DTO, запрет клиентской цены и чужих рынков;
- риск с обеими комиссиями, notional, одна позиция, drawdown, откат отклонённых операций;
- stale/future/source-mismatched quote, таймаут, HTTP 302/403/429/500, часы, слишком большой/некорректный ответ;
- quote expiry во время ожидания транзакции;
- одно и то же/разные намерения с одним ID, одновременные команды разных store instances;
- rollback до commit, потеря ответа после commit, повтор без доступа к рынку;
- SL/TP LONG/SHORT, неблагоприятный gap по наблюдаемой цене, отсутствие двойного выхода;
- повреждение/исчезновение состояния, чужая БД, append-only receipts;
- запрет ephemeral storage на Render и проверка конфигурации mount;
- отдельные Python-процессы с реальным SQLite-файлом;
- настоящий HTTP/Uvicorn сервис: вход → остановка процесса → новый процесс → сохранённая позиция → закрытие → ещё один restart → неизменные баланс и история.

**4 новых JavaScript-теста — PASS.** Исполняют actual UI script с DOM/storage/fetch fixtures: запрет stale/foreign данных, один виртуальный счёт, потеря ответа и reload с тем же ID, запрет отправки при невозможности сохранить request ID.

Дополнительно: `node --check`, AST parse всех Python-файлов, импорт `app.main`, `git diff --check`, проверка intended diff на секреты и границы доступа.

Полный локальный regression: **1938 passed, 3 skipped, 0 failures, 0 errors** (1941 testcases, 104,857 с), результат подтверждён JUnit XML. Пропуски — только три существующих PostgreSQL suites, перечисленных ниже. **Все 268 JavaScript-тестов — PASS**, 0 skips/failures.

Среда: Python 3.12.14, Node 24.22.1 (локально отличается от `.node-version` 24.19.0; удалённый CI использует версию репозитория). Основные runtime-зависимости соответствуют `requirements.txt`. Прокси окружения убраны только в командах локального тестирования: иначе baseline запуск падал при создании HTTPX из-за отсутствующего SOCKS-пакета; production-код ради этого не менялся.

Удалённый GitHub regression CI проверяется для итогового commit PR. Это отдельное доказательство, не подменяемое локальным запуском. Локально полный zero-skip gate проекта не заявляется пройденным из-за трёх PostgreSQL skips.

## Отдельный code review

Проверены API → quote adapter → network-free commands → transaction → decode/accounting → frontend retry, а также lifecycle/cancellation и обратные зависимости. Исправлены подтверждённые находки из таблицы. Active43, его стратегии, storage, API, scheduler, workflow и переменные не меняются. В `app/main.py` добавлен только отдельный Manual Paper router/lifecycle; существующий контроллер вызывается как прежде. Зависимости runtime не меняются.

## Отдельный security review

Проверены owner и same-origin на обеих mutation routes, полное исключение клиентской execution price, фиксированные HTTPS public GET Bitget с redirects disabled, конечные/положительные числа, ограниченный ответ и таймаут, проверка свежести внутри транзакции, неизменяемые ключи повторов, scope базы, mount confinement, редактирование текста через textContent и отсутствие секретов в новых клиентах/журнале. API не имеет reset, topup, режима real или обменных order endpoints. Engine/commands/store не импортируют HTTP/exchange clients.

После исправлений нерешённых подтверждённых Critical/High ошибок не обнаружено. Это отдельные проходы проверки в этой сессии, не внешний независимый аудит.

## Оставшиеся условия выпуска

1. Production не развёрнут, PAPER не включён, позиции production не открывались. Слияние/deploy не выполняются этой задачей.
2. Для выбранного backend нужен постоянный диск на платном Render service. Его фактическое монтирование и restart-readback на Render пока не проверены. На ephemeral storage модуль останется заблокированным.
3. Live Bitget connectivity из Render не проверена этой задачей: автоматические тесты используют mocks/loopback. Никаких production-секретов в тестах нет.
4. Визуальный прогон Chromium на мобильном viewport — **NOT RUN**: браузер не установлен; загрузка browser package завершилась ошибкой. DOM/interaction tests пройдены, адаптивная CSS-разметка подготовлена, но визуальный вид на реальном телефоне не заявляется проверенным.
5. SL/TP зависят от работающего сервера, свежего Bitget и доступной БД; не гарантируются точная цена и историческое касание во время простоя. Funding/глубина стакана не моделируются.
6. Три существующих PostgreSQL integration suites локально пропускаются без disposable Docker/PostgreSQL. Это не тесты выбранного Manual Paper SQLite backend. Полный CI проекта требует их выполнения на GitHub runner.

Инструкция выпуска и точные ограничения: [MANUAL_PAPER_V1.md](MANUAL_PAPER_V1.md).


## Финальный аудит перед запуском — 26.10.2026

Проверен исходный CI на `507d3fe`: [Regression CI #69](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40305977390), **1941 Python + 268 JavaScript, 0 failures/skips**. После изменений ниже требуется CI на новом head; источник окончательного результата — последний head/run в PR #57.

Дополнительные подтверждённые проблемы и исправления:

- Проверка persistent mount ранее выполнялась только при старте. Теперь перед каждым SQLite connect: потеря mount/подмена пути блокирует доступ до создания файла. Тесты подтверждают отсутствие временной базы и восстановление того же баланса после возврата mount.
- Повреждённая структура JSON (например, список сделок из чисел) могла вызвать AttributeError и завершить защитный цикл. Decode теперь нормализует повреждение в CORRUPT_JOURNAL; API безопасно возвращает 503, а цикл остаётся жив и не меняет счёт.
- Добавлен `scripts/manual_paper_preflight.py`: read-only конфигурация, проверка mount/прав/существующего журнала, свежий публичный Bitget ticker; без account seed и без Active43. Отдельные offline-тесты проверяют отсутствие записи и вывода секретов.

Финальные отдельные code/security review охватывают эти изменения, актуальные owner/CSRF зависимости, источник/свежесть цены, ограничения риска, позиционный ID, permanent receipts, атомарность SQLite, restart, SL/TP и fail-closed обработку ошибок. Нерешённых подтверждённых Critical/High в Manual Paper не найдено. Утверждение не включает внешний аудит и фактический production mount.

Render прочитан через подключённый инструмент: Free, Virginia, один инстанс, auto-deploy Off, live b721a0c. Health 200. Owner endpoint 401 без авторизации. Публичный market endpoint вернул 500 свежих 1m Bitget Futures candles (`stale=false`). Переменные Manual Paper не прочитаны: env GET отсутствует в инструменте, browser dashboard требует входа. На Free постоянный disk не поддерживается; текущий runtime mount не проверен. В логах Active43 есть HISTORY_CANDLE_CHANGED и RATE_LIMIT; его код, режим и настройки не менялись.

Базовый бюджет выбранной конфигурации — 7.25 USD/месяц при web 0.5c-512mb и disk 1 GB, до налогов/дополнительного расхода. Платные действия, merge и production deploy не выполнялись.

**Пошаговый порядок, настройки, безопасные точки остановки и проверка Android:** [MANUAL_PAPER_LAUNCH_RUNBOOK.md](MANUAL_PAPER_LAUNCH_RUNBOOK.md).


Результаты дополнительных offline-проверок перед публикацией: **109 тестов Manual Paper — PASS**, включая 14 новых проверок mount loss, повреждённой структуры и read-only preflight (включая запрет чужой SQLite-схемы). Полный локальный Python после первых двух исправлений: 1946 passed / 3 existing PostgreSQL skipped / 0 failures; все 268 JavaScript — PASS. Полная проверка всех последующих файлов выполняется GitHub CI для нового head.

Попытка безопасного входа в Dashboard завершилась таймаутом браузерного инструмента и сбросом его сеанса. Результат авторизации не подтверждён, содержимое env не прочитано; отсутствие или конкретные значения Manual Paper переменных не заявляются проверенными. До запуска нужна отдельная сверка таблицы Environment.

## Бесплатный backend Supabase — текущий рекомендуемый вариант

**CI бесплатного backend — PASS:** [Regression CI #72](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/40320837030) проверил runtime commit `e12f83672da0bcbec4f9bde5374e98cbbbf2a104`: **1976 Python + 268 JavaScript, 0 failures и 0 skips**. Включены все четыре настоящих PostgreSQL harness, новый Manual Paper — 10 сценариев, в том числе restart, same-ID/different-ID concurrency, RLS/ACL и истечение quote под SQL lock. JUnit/summary загружены артефактом этого run. Один существующий Starlette/AnyIO deprecation warning; не скрыт. Python CI 3.12.15, локально 3.12.14; Node CI 24.19.0, локально 24.22.1.

Дополнительно read-only `get_organization` подтвердил у существующей организации Supabase `plan=free`, `tier=tier_free`. План и платные подписки не менялись. Базовый бюджет нового варианта — **0 USD/месяц в пределах квот**, а не исторические 7,25 USD для SQLite disk.

Этот раздел и новый launch runbook заменяют требование оплаты SQLite-диска из предыдущих исторических разделов. Теперь можно использовать **Render Free + существующий Supabase Free** в пределах лимитов, без платных услуг. SQLite остаётся дополнительным локальным/persistent-disk backend.

Добавлены отдельный Supabase Store и additive SQL-схема `aura_manual_paper_v1_*`, RLS/ACL для server-only доступа, SECURITY INVOKER RPC, атомарные CAS + permanent receipts, проверка свежести по часам PostgreSQL после ожидания lock, checksum и повтор без рынка при неизвестном результате. Нет автоматического fallback или сброса баланса. Для экономии трафика одинаковые версии возвращают метаданные вместо полного снимка. Payload ограничен 1 MiB с резервом закрытия; все receipts сохраняются.

Существующая Aura проверена **только чтением**: ACTIVE_HEALTHY, PostgreSQL 17, база 17,42 MB, новых Manual Paper таблиц пока 0. Подготовленная SQL-схема в рабочую базу не применялась. Render, его тариф/env и Active43 не менялись. Никаких production-позиций не открывалось.

Добавлены offline HTTP/API тесты Supabase: LONG/SHORT и fees, потерянный ответ после commit, повтор/конфликт ID, cache revalidation, CAS retry, свежесть, source/scope, отсутствие локального fallback, неправильные ответы/HTTP auth/rate errors, redaction, новые secret key и legacy JWT headers. Preflight поддерживает remote read без создания account.

Новый настоящий PostgreSQL harness запускается CI в выделенном labelled Docker container, `network=none`, без production-ключей. Он проверяет SQL-схему и повторное применение на заполненном счёте, RLS/ACL, запрет browser-ролям, отсутствие SECURITY DEFINER, LONG/SHORT/fees, restart, permanent idempotency, конкурентные команды, истечение quote под SQL lock и неизменность существующих Active43 function definitions. HTTP/PostgREST wire проверяется отдельно mocked transport; реальный Supabase gateway ещё не проверен после согласованной установки.

Финальные code/security review: runtime Store/RPC/SQL/Service/lifecycle и UI не имеют доступа к существующему Active43 состоянию; engine/commands и SQLite Store остаются без сетевых клиентов. Server key только на backend, fixed Supabase URL/allowlisted RPC, redirects запрещены, ответы/таймауты ограничены и ошибки санитизированы. Математика риска и owner/CSRF не менялись. Новых подтверждённых нерешённых Critical/High не найдено; runtime/env и post-deploy проверки остаются условиями выпуска.

Бесплатные ограничения: пока Render спит, SL/TP не проверяются; квоты Supabase общие, проект Free может быть приостановлен при неактивности. До запуска нужны отдельное согласование SQL, env и deploy, проверка текущего Active43 перед restart, фактические свежие quotes и телефон. **Платный тариф не требуется для нового backend.**

Актуальный CI должен быть зелёным для последнего SHA PR #57. Детали бесплатного запуска: [MANUAL_PAPER_LAUNCH_RUNBOOK.md](MANUAL_PAPER_LAUNCH_RUNBOOK.md).


Отдельный code review бесплатного backend выявил и исправил гонку same-ID между lookup и load: ошибка уже открытой позиции теперь повторно проверяет permanent receipt. Детерминированный offline regression проверяет этот порядок, а настоящий SQL CI отдельно проверяет конкуренцию разных клиентов. Лимит payload протестирован с запретом новых входов и доступным закрытием. Неправильный тип remote payload нормализован в CORRUPT_JOURNAL.

Security review отдельно проверил owner/CSRF на всех mutation routes, отсутствие client price, fixed Bitget/Supabase endpoints, TLS/redirects, хранение server key, отказ browser-ролям, транзакционное сохранение состояния/receipt и DB-clock gate после lock. Реальный Supabase gateway, production env и физическая проверка телефона до согласованного выпуска — NOT RUN. Отдельная проверка синтаксиса всех Python, import app.main, node --check, diff whitespace и поиск секретов в изменениях — PASS. Node 24.22.1 локально вместо CI 24.19.0; один существующий warning Starlette/AnyIO, новых dependencies нет.

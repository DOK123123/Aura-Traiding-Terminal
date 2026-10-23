# Aura 4.3: scheduled off_only, 23 октября 2026

Основа: main `693cd28a11640ff5d81dacffe7748d71a5e7b16e`, PR #27 объединён.
Его исправление DIAGNOSTICS_BLOCKED уже присутствует, но operation=off_only
вообще не проходит эту ветку. Поэтому оно не объясняет нынешний off_only exception.

## Что установлено

В исходном main воспроизведены два дефекта транспорта:

1. После получения HTTP 200 таймаут чтения тела превращался в INVALID_RESPONSE,
   как некорректный JSON/loading-HTML, и добавлял cold-start задержку. Теперь
   сигнал AbortController даёт REQUEST_TIMEOUT, phase=BODY; ошибка не скрывается.
2. Для HTTP 200 с некорректным телом обработчик повторно устанавливал retry=true,
   даже когда Retry-After уже запретил повтор в пределах бюджета. Контрольный
   пример Retry-After=999999 давал две попытки в исходном main; теперь — одну.
   Исключение остаётся INVALID_RESPONSE, раннего повтора нет.

Это **не доказанные причины конкретного production exception с wallTimeMs=8285**.
По одному wall time нельзя отличить auth, ответ сервера, контракт, сохранение,
ошибку runtime или CPU limit. Прямого доступа к аккаунтам Cloudflare/Render,
секретам, версии опубликованного Worker и его trace в этой среде нет.

## Диагностика

Перед каждым fetch добавлен REQUEST_STARTED. Он содержит только фиксированный
endpoint, operation, attempt, http_status=null и code. Теперь понятно, начал ли
Worker обращение до появления сетевой ошибки. REQUEST_FAILED сохраняет код и
добавляет phase: REQUEST, BODY, HTTP_STATUS, CONTRACT или SERVER_DECISION.

Все события содержат component=ACTIVE43_FREE_SCHEDULER,
worker_version=ACTIVE43_CF_2026_10_23 и scheduled_time (milliseconds UTC либо null).
Версия — идентификатор этого кода, не commit и не fingerprint секрета.
События остаются application console logs, а не системными cf-worker-event.
В Cloudflare Observability → Logs ищите полным текстом **ACTIVE43_FREE_SCHEDULER**
или **ACTIVE43_CF_2026_10_23**, не ограничивая выборку одним cf-worker-event.

Ожидаемая цепочка для успешного off_only:

`REQUEST_STARTED → RENDER_REACHED (200) → TICK_SAVED`

У TICK_SAVED обязательны status=COMPLETED, operation=off_only, mode=OFF,
opened=closed=0, state_saved=true. Два разных scheduled_time через 300000 ms
означают разные Cron-события; две attempt одного события — только retry.

Auth/сеть/контракт/PAUSED tick по-прежнему завершаются отказом. BLOCKED diagnostics
остаётся BLOCKED, а не PASS. DISABLED не выполняет HTTP. Raw body/headers,
токены, private exception messages, балансы и позиции в Worker не выводятся.

## Сквозная изолированная проверка

Новая fixture `tests/fixtures/active43_scheduled_wire.mjs` вызывает настоящий
Worker.scheduled(), а не только run(). Только тестовый fetch-adapter направляет
фиксированный off_only URL на loopback HTTP server. Production Worker host/path
не меняются. Fixture принимает только localhost и DUMMY_ token, mode фиксирован
на off_only; app/main не импортирует и не публикует этот контур.

Существующий verifier запускает:

`scheduled() → HTTP → FastAPI scheduler auth → verify_off_tick → Service → Store → SQL RPC`

PostgreSQL — реальный отдельный Docker-контейнер с network=none и ограниченными
ресурсами; HTTP Supabase заменён мостом к его SQL, это не hosted PostgREST.
Проверяется первый слот, повтор того же слота и второй слот через **виртуальные**
300 секунд после перезапуска PostgreSQL/Service. Результат: два новых TICK,
повтор без новой записи, mode OFF, OPEN/CLOSE=0, state_saved=true. Баланс, equity,
комиссии, slippage, realized PnL, статистика и признаки позиций/операций совпадают
до и после. Это не два события настоящего Cloudflare Cron и не production proof.

Вне этого verifier PostgreSQL/HTTP server не запускаются. RENDER guard запрещает
запуск контура на Render; никаких тестовых production endpoint или сигналов нет.

## Production и ограничения Free

В этой задаче выполнены только GET /api/health и GET /openapi.json на Render:
оба HTTP 200, POST-маршруты verify-off-tick, tick, diagnostics/scheduler
зарегистрированы. Токены не использовались, tick/control/initialize не вызывались.
Это **LOCAL_TO_RENDER**, не CLOUDFLARE_TO_RENDER и не проверка записей Supabase.

Лимиты не изменены: Free CPU 10 ms, Cron wall time до 15 min, 50 subrequests;
наш максимум — две попытки, до 120 s каждая, общий бюджет до 240 s, ответ до 32 KiB.
Cron `2-59/5 * * * *` UTC и flags false/diagnostics в шаблоне не менялись.
Awaited scheduled handler допустим; причина не установлена как «нет waitUntil».
Реальный workerd CPU и Cloudflare limits в этой среде не измерены. Cold start
Render, free-tier sleep и ограничения платформ остаются best-effort, не SLA 24/7.

## Владельцу после Merge: три действия

1. Обновить **код существующего aura-active43-scheduler** в Cloudflare Edit code
   полным worker.mjs из main и опубликовать в этом Worker. Не создавать новый,
   не применять шаблон с другим name. Render Deploy, SQL, новые env/ключи не нужны.
2. Сохранить PAPER OFF; в read-only Owner Panel подтвердить OFF, отсутствие
   позиции/pending/pending_exit и guards PASS. Не выполнять START/STOP/RESET или
   initialize. Существующие off_only, разрешение Cron и секреты здесь не меняются.
3. Дождаться двух разных настоящих Scheduled событий и проверить описанные
   TICK_SAVED/COMPLETED/OFF/0/0/state_saved=true. Если снова exception, оставить
   PAPER OFF и предоставить безопасные application logs этого scheduled_time:
   REQUEST_STARTED/RENDER_REACHED/REQUEST_FAILED с code/http_status/phase/version,
   плюс system exception name/message и cpuTimeMs/wallTimeMs. Для HTTP-ошибки нужны
   соответствующие Render path/status/code за это время, без raw body, headers
   и секретов. По этим данным отделяется авторизация, БД, контракт и runtime.

## Review

Code review: только транспорт/диагностика Worker и изолированные проверки;
server endpoints, engine, стратегия, risk, Store, SQL и cron-config неизменны.
Security review: фиксированные host/path/header, redirects manual, whitelist
логов, нет нового публичного API, тестовая сеть только loopback/Docker network none.
Повторы и ошибки не считаются Success. Критических/high замечаний не найдено.
Aura 4.2/Practice, production balance/positions/history и настройки не менялись.
Merge и Deploy не выполнялись, PAPER и Cron не включались этой работой.

PRODUCTION_OFF_ONLY_CYCLES_VERIFIED = FALSE

PRODUCTION_PAPER_VERIFIED = FALSE

## Результаты тестов ветки

- Полный Python suite: **1560 passed, 3 skipped**, 119,09 s. Пропуски — opt-in
  PostgreSQL suites Auto42, Practice и Active43 в этом обычном запуске.
- Отдельный opt-in Active43 PostgreSQL suite на окончательной версии: **4 passed**,
  93,33 s; 14 групп SQL/RLS/atomicity/restart проверок и 7 существующих сценариев
  исполнения. Это дополнительно исполняет пропущенную выше SQL-проверку.
- Полный Node suite: **236 passed**, включая 24 Worker-теста.
- Новая сквозная проверка: 3 scheduled handler вызова, 2 сохранённых слота,
  middle duplicate=true без записи, PostgreSQL/Service restart PASS,
  financial state unchanged, events_added=2.
- AST 231 Python-файл, import app.main, node --check Worker/fixture,
  git diff --check: PASS. Одно существующее Starlette/anyio deprecation warning.
- Cloudflare runtime CPU, два настоящих production scheduled off_only и
  production Supabase записи от нового Worker: NOT VERIFIED.

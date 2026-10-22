# Aura 4.3: бесплатный Cloudflare Workers Cron → Render Paper API

Статус: код подготовлен; **Cloudflare deploy и настоящий scheduled вызов не выполнены**.
PAPER, внешние scheduler и платные ресурсы этой работой не включались. Aura 4.2 и
Paper Practice не меняются. Уже существующий `deploy/auto42-worker/` оставлен как есть;
для 4.3 используется другой Worker, secret binding и API namespace.

## Обновление уже существующего Worker

Для текущего `aura-active43-scheduler` **не создавайте новый Worker** и не запускайте
слепо `wrangler deploy` с именем из шаблона. Исправление диагностики публикуется
в существующем Worker владельцем после Merge. Production-настройки в этой работе
не изменяются, новые ресурсы/ключи не нужны. Подробные события, доказательства,
ограничения Free и процедура двух off_only циклов:
[DIAGNOSTICS_VERIFICATION.md](DIAGNOSTICS_VERIFICATION.md).

## Выбор, цена, карта и Россия

Проверка официальных источников: 2026-10-20.

| Вариант | Бесплатный запуск каждые 5 минут | Карта / ограничения | Вывод |
| --- | --- | --- | --- |
| **Cloudflare Workers Free + Cron Trigger** | Да; один trigger, 288 событий/сутки | Cloudflare заявляет регистрацию без карты; Free: 100000 запросов/сутки, 5 cron/account, 10 ms CPU/invocation, 50 subrequests; до 15 минут wall time для cron | Выбран для лёгкого HTTP-dispatch; расчёт стратегии остаётся на Render |
| cron-job.org | Да, FAQ разрешает до одного запуска/минуту, сервис бесплатен | 30 секунд ожидания; headers/POST поддержаны; регистрация и доступ из РФ лично не проверены | Прямой вызов может обрываться раньше cold start + tick; не выбран |
| Google Cloud Scheduler | 3 jobs бесплатно на billing account; частота не тарифицируется отдельно | Требуется включённый Cloud Billing; доступность создания billing account и платежного метода из РФ здесь не подтверждена | Не выбран для варианта без платёжной настройки |
| GitHub Actions schedule | В публичном repo доступен без подписки | В этом проекте события schedule доставлялись с большими пропусками | Не основное решение |
| Render Web сам по себе | Не даёт надёжного фонового scheduler на Free | Сон/перезапуски; нельзя считать вечный цикл внутри web автономным | Используется только как API исполнения |

Источники: [Workers Free/no-card](https://www.cloudflare.com/products/workers/),
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[cron-job.org FAQ](https://cron-job.org/en/faq/),
[Google Scheduler pricing](https://cloud.google.com/scheduler/pricing),
[Google Scheduler billing requirement](https://docs.cloud.google.com/scheduler/docs/schedule-run-cron-job).
Сервисы, требующие платную подписку для пяти минут, не предлагаются.

**Цена выбранного scheduler — 0 ₽ при Workers Free и соблюдении общих квот аккаунта.**
Платные Workers, R2, KV, D1, Durable Objects, Queues, Workflows, домен и подписки
не нужны. I/O-ожидание не расходует CPU лимит; все индикаторы/сделки выполняет Render.
При 288 событиях и максимум двух попытках — до 576 исходящих HTTP-запросов/сутки,
не больше двух subrequests на событие. Реальное потребление CPU Cloudflare ещё не
измерено; Node-тесты не доказывают прохождение 10 ms лимита Workers Free.
Квоты общие с другими Worker аккаунта, включая существующий Aura 4.2, если он развёрнут.

Доступность из России нельзя обещать: [Cloudflare описывает ограничения российских
ISP](https://blog.cloudflare.com/russian-internet-users-are-unable-to-access-the-open-internet).
Открытие Dashboard/регистрация с сети владельца **NOT VERIFIED**. Сам Cron выполняется
в облаке, не на компьютере владельца и не через его домашнее соединение; но это не
гарантия доступности аккаунта/сети/провайдера. Регистрация и Cloudflare → Render
проверяются владельцем до PAPER ON. Если регистрация недоступна, этот кандидат
нельзя объявлять работающим решением для конкретного владельца.

## Сон Render и предел надёжности за 0 ₽

[Render Free](https://render.com/docs/free) засыпает через 15 минут без входящего
трафика; пробуждение занимает примерно минуту. API получает настоящий scheduler
POST, а не пустой keep-alive. Интервал 5 минут обычно предотвращает idle sleep,
но Render всё равно может перезапустить/приостановить free instance. Новый endpoint
для fast-ACK/fire-and-forget не добавляется: успешный ответ требуется **после** DB commit.

Worker ждёт до 120 секунд на попытку, включая чтение ответа. Обычно это больше
cold start + 50-секундный бюджет server tick, однако верхней гарантии cold start нет.
При HTML loading page или временном gateway 502/503/504 повтор ждёт минимум
60 секунд, чтобы не исчерпать попытки до пробуждения. Максимум две попытки, общий
бюджет 240 секунд, поздние события имеют меньший бюджет.
Сбой/таймаут не считается успехом. Следующий cron может восстановить доставку;
при остановленном Render виртуальные SL/TP не исполняются, а новые входы запрещены
при непроверенных данных/БД существующим controller.

750 free instance-hours Render в месяц — общая квота workspace. Один постоянно
работающий web за 31 день использует до 744 часов; другие free web могут исчерпать
остаток. Контролировать Render usage, Supabase storage/egress и действующие free
лимиты. Точный биллинг аккаунтов этой сессии недоступен: нельзя гарантировать
нулевой общий счёт при уже подключённых платных услугах или перерасходе.
Новые платные планы не включать. Бесплатная связка обеспечивает best-effort
автоматизацию, **не SLA/гарантию 24/7**.

## Код и безопасность

`worker.mjs` содержит только outbound scheduled handler и HTTP handler с 404.
`wrangler.jsonc` отключает workers.dev/preview URL. Публичного API запуска нет.
Фиксированы host, пути `/api/active43/…`, метод POST и header
`X-Aura-Active43-Bitget-Token`. Redirects не следуются; секрет не передаётся в URL,
логи, ответы или иные хосты. Worker не получает Supabase key, owner password либо
Bitget trading keys и не вызывает START/STOP/RESET/initialize.

Secret binding `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` — **то же существующее значение**
из Render, скопированное владельцем приватно в Cloudflare Secret. Новый токен не
генерировать и рабочий Render/GitHub secret не заменять. Это ограниченная scheduler
авторизация только для Aura 4.3 Paper, а не owner control или биржевой доступ.

Режимы:

- `AURA_ACTIVE43_CRON_ENABLED=false` (default): cron только пишет DISABLED, без HTTP.
- При enabled=true, `AURA_ACTIVE43_OPERATION=diagnostics` (default) — только read-only
  `/diagnostics/scheduler`. Корректный BLOCKED даёт DIAGNOSTICS_BLOCKED без исключения
  доставки; готовность остаётся BLOCKED, а не PASS. Ошибки auth/сети/контракта остаются ошибками.
- `off_only` — существующий `/verify-off-tick` с фиксированным confirmation. Требуются
  пустой OFF-счёт и серверные risk guards; OPEN/CLOSE должны быть 0. Не инициализирует счёт.
- `saved_mode` — существующий `/tick`; соблюдает сохранённые ON/OFF/PAUSED/EMERGENCY.
  Он не включает PAPER сам. Это будущий торговый режим только после разрешения.

Проверяются Bitget v3 scope/source, paper_only, exchange_execution=false, state_saved,
режим, счётчики, watermark и read-only/off-only признаки. Неверный JSON, oversized
ответ >32 KiB, ложные safety flags и чужой scope не считаются успехом. PAUSED после
подтверждённого сохранения не повторяется немедленно. 401/403, redirects и известные
ошибки авторизации/схемы завершаются без повторов; временные ошибки получают максимум
один повтор. Retry-After соблюдается; если ожидание не помещается в бюджет, повтор
не выполняется раньше времени. Просроченные scheduled события не воспроизводятся.

Worker stateless: он не создаёт нового ledger и не требует распределённой БД
Cloudflare. Финансовая защита между разными вызовами/инстансами — существующие
Supabase CAS revision, уникальный 5-минутный tick key, атомарный state/events и
receipt readback. Таймаут клиента не доказывает отмену server tick. Повтор может
вернуть duplicate=true; при переходе в другой временной слот это новый безопасный
tick, а не обещание того же duplicate ID. Одна позиция/уникальные события предотвращают
повторное финансовое исполнение. Параллельные чтения возможны, двойные scheduler
без необходимости держать не нужно.

## Однократная настройка владельцем после review/Merge

Deploy в этой задаче запрещён и не выполнен. Доступа к аккаунту Cloudflare/его
регистрации в этой сессии нет. Понадобится разовая настройка; потом компьютер не нужен.

1. В [Cloudflare Dashboard](https://dash.cloudflare.com/) создать **Workers & Pages →
   Create Worker** на **Workers Free**. Имя `aura-active43-bitget-free-scheduler`,
   вставить полный `worker.mjs` из этой папки. Не изменять Worker Aura 4.2. Добавить
   Secret `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` с текущим Render значением приватно.
2. В Variables задать `AURA_ACTIVE43_CRON_ENABLED=false`,
   `AURA_ACTIVE43_OPERATION=diagnostics`. Добавить Cron Trigger
   `2-59/5 * * * *` (UTC); отключить workers.dev и preview URL. Конфигурация готова
   в `wrangler.jsonc`; через CLI её можно применить после отдельного разрешения
   командой `npx wrangler deploy` из этой папки. Секрет вводится через Dashboard
   либо `npx wrangler secret put AURA_ACTIVE43_BITGET_SCHEDULER_SECRET`, без ключа в argv.
3. После разрешения **только проверки scheduler**, убедиться в Owner Panel, что
   PAPER OFF и позиции/ожидающих операций нет. Выключить только старый Aura 4.3
   GitHub scheduler variable и новый платный Render Cron, если владелец успел его
   создать; не затрагивать Aura 4.2. Затем выбрать `AURA_ACTIVE43_OPERATION=off_only`,
   `AURA_ACTIVE43_CRON_ENABLED=true` и дождаться **двух реальных Cron invocations**:
   `TICK_SAVED`, mode OFF, state_saved=true, opened=closed=0. Изменения trigger могут
   распространяться несколько минут (Cloudflare предупреждает о задержке до 15 минут).

Не публиковать значения секретов, raw request headers или приватные dashboard
скриншоты. Платный Render Cron не нужен; код его шаблонов остаётся как историческая
альтернатива. Созданный ранее платный сервис продолжает иметь свой биллинг до
действий владельца — новый Worker не удаляет/останавливает чужие ресурсы.

### Допуск PAPER — отдельно, не часть этой задачи

После подтверждённых scheduled OFF ticks и нового разрешения: сначала установить
`AURA_ACTIVE43_OPERATION=saved_mode`, сохраняя PAPER OFF. Проверить очередной
обычный tick mode OFF, затем только через Owner Panel разрешить START PAPER.
Иначе off_only при ON будет безопасно отказывать и не сможет сопровождать позицию.
На естественном сигнале проверить OPEN → UPDATE → CLOSE в Supabase, без тестовых
сигналов. Хранение, комиссия, риск, SL/TP и восстановления остаются существующими.

Аварийно: Owner STOP/EMERGENCY сохраняет запрет новых входов. При открытой позиции
оставить scheduled `saved_mode` для защитных выходов. После подтверждённого закрытия
можно установить `AURA_ACTIVE43_CRON_ENABLED=false`. Остановка scheduler не закрывает
позицию; недоступная БД не позволяет подтвердить сохранение STOP. Не сбрасывать SQL.

## Проверки и production-доказательства

- Node-тесты моделируют cold start/abort, bounded retry, duplicate, PAUSED, ошибки
  auth/redirect/source/БД-контракта, retry cooldown, stale cron и закрытый HTTP handler.
  Это тесты транспорта, не естественные сделки и не измерение CPU Workers.
- Полный Python-набор с настоящим локальным PostgreSQL проверяет существующий
  финансовый путь, RLS, concurrency, OPEN/CLOSE, fees/PnL, restart и legacy isolation.
- Проверка настоящего Render API: health=200; unauthenticated `/tick` и
  `/verify-off-tick` =401 / SCHEDULER_TOKEN_MISSING, до execution.
- [Actions diagnostics #28](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39453246162)
  через работающий Render: Bitget/Supabase CONNECTED, stage COMPLETE; scheduler
  STALE_TICK, status BLOCKED, state_changed=false, production_paper_verified=false.
  Job success — только доставка диагностики. GitHub periodic variable на этом run true,
  но это не доказывает событие schedule. В этой задаче production tick/control не вызывались.
- **Не проверено:** регистрация и Dashboard из РФ, Cloudflare deploy, доступ именно
  Cloudflare → Render, Free CPU на реальном runtime, wake-up после настоящего idle
  сна, two scheduled OFF runs, 24–48 часов автономности и natural production OPEN/CLOSE.

**Архивная проверка первоначального PR #24: 1532 Python passed, 2 skipped; 223 JavaScript passed, включая 15 новых.**
Реальный локальный PostgreSQL выполнен, legacy accounts/functions неизменны.
Два skip — opt-in suites старых Auto42/Practice; единственное предупреждение —
существующий Starlette/AnyIO deprecation. Syntax/app import/diff checks прошли.

Новый endpoint, миграция, сброс баланса, изменение Aura 4.2/Practice и платная
подписка не нужны. Итоговые тесты/флаги: `VERIFICATION.json` в этой папке.

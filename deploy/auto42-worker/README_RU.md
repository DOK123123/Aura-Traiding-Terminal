# Внешний scheduler Aura 4.2: Cloudflare Workers Cron

Статус: ПОДГОТОВЛЕН, НЕ РАЗВЁРНУТ И НЕ ПРОВЕРЕН В CLOUDFLARE.
Работа автоматического расписания не подтверждена. START PAPER пока не нажимать.

## Выбор

Отдельный Worker вызывает фиксированный HTTPS POST
https://aura-traiding-terminal.onrender.com/api/auto42/tick каждые пять минут
(:02,:07,...,:57 UTC). Он проверяет не только HTTP 200, но и PAPER_ONLY,
отсутствие exchange execution, state_saved и контракт обработки свечи.
При провале выполнение завершается ошибкой, журнал не выдаёт успех за отказ.

cron-job.org поддерживает headers/POST бесплатно, но FAQ указывает timeout
30 секунд. Это меньше возможного cold start Render + tick, поэтому прямой
вызов этого сервиса не выбран. Cloudflare Cron — подходящий кандидат для
бесплатного небольшого scheduler, но тарифные лимиты/доступность необходимо
проверить в аккаунте при развёртывании; SLA 24/7 не обещается.
Обращение к документации Cloudflare из текущей среды получило HTTP error,
реального исполнения Worker нет. Расходы не подключались.

## Что уже подготовлено

- worker.mjs: POST только на один fixed host/path; секрет только в header;
  redirect manual, отсутствует публичный endpoint запуска.
- wrangler.jsonc: UTC cron, отключены workers.dev/preview URLs, включены logs.
- AURA_AUTO42_SCHEDULER_SECRET: имя secret binding, значение того же существующего
  Render scheduler secret. Не owner password, не Supabase key и не exchange key.
- 120 секунд на запрос, включая чтение JSON; максимум три попытки, backoff 2/4 s.
  Превышение 64 KiB, неверный контракт или authorisation fail закрывают запуск.
- Структурированные логи содержат только enum outcome/mode/code, HTTP status,
  attempt и счётчики. Исключения, headers, токен и сырой ответ не выводятся.
- Ошибка временной сети допускает retry; следующий cron также восстанавливает
  вызовы. Worker не отправляет START, STOP, RESET или EMERGENCY.

## Одно необходимое действие владельца: развернуть этот Worker

В доступных подключениях нет Cloudflare account/deploy API. Не присылайте secret
в чат. Сделайте настройку в собственном Cloudflare аккаунте:

1. Workers & Pages → создать Worker `aura-auto42-scheduler` и вставить содержимое
   worker.mjs в редактор. На этом этапе не добавлять cron.
2. Settings → Variables and Secrets: добавить SECRET binding
   `AURA_AUTO42_SCHEDULER_SECRET`, скопировав существующее значение из Render.
   Обычная открытая variable не подходит. Секрет не менять.
3. Deploy Worker, затем Settings → Triggers / Cron Triggers:
   `2-59/5 * * * *`. Названия пунктов могут отличаться в версии панели.
   Выключить публичный workers.dev/preview URL; fetch всё равно отвечает 404.
   Для CLI эквивалентные настройки находятся в wrangler.jsonc.
4. Оставить Aura OFF. Проверить несколько РЕАЛЬНЫХ scheduled executions в logs:
   AUTO42_TICK_CONFIRMED, mode=OFF, outcome=HEARTBEAT_OFF или NO_NEW_WORK,
   opened=0. Сопоставить с сохранением/временем tick в Aura. Ошибка должна
   появляться как failed execution, а не зелёный HTTP 200.

GitHub scheduler не отключён. Параллельная работа безопасна по существующим
контролям backend: singleflight в процессе, durable tick key на 5-минутный слот,
CAS/revision и PostgreSQL row lock, atomic event/portfolio commit, candle watermark.
Защита действует на разных экземплярах, а не только внутри Worker.
Это предотвращает двойное исполнение; не гарантирует отсутствие параллельных
HTTP-запросов/вычислений между двумя провайдерами. Отдельный внешний lock не нужен
для финансовой атомарности. Retry после неизвестного исхода заново проверяет
сохранённый operation key. Никаких новых таблиц и миграций.

После 24 часов наблюдения, проверки задержек/ошибок можно отдельно отключить
старый GitHub cron. Сейчас это не сделано. Не путать зелёный OFF heartbeat
с доказательством успешной рыночной сделки. Без реального сигнала сделок быть
не должно. Включение портфеля требует отдельной команды владельца.

## Проверка виртуальной цепочки

Существующий tests/test_auto42.py проверяет замкнутый цикл production strategy
на synthetic fixtures: signal → pending → next closed execution bar → fees/PnL
→ journal, а также два concurrent Service, restart, STOP/EMERGENCY races.
Это тесты алгоритмов, не искусственные сигналы в production.
Supabase SQL использует SELECT FOR UPDATE, revision CAS, уникальный operation key
и append-only events. Реальная проверка PostgreSQL конкуренции здесь недоступна.
Node tests/test_auto42_worker.cjs проверяет новый HTTP adapter, retry/timeout,
no secret leak, duplicate acknowledgement, auth, unsafe/oversized/malformed reply.

Render deploy и изменение backend не требуются. GitHub Auto-Deploy может
самостоятельно сработать на commit. Worker deploy агент не выполнял.
Точный backend SHA Render публично не сообщается; версия не угадывается.

Источники:
https://cron-job.org/en/faq/
https://developers.cloudflare.com/workers/configuration/cron-triggers/
https://developers.cloudflare.com/workers/platform/limits/

## Результаты проверки реализации

Полный Python suite: 1114 passed, 0 failed, 1 deprecation warning, 79.69 s.
Все 11 Node suites: 161 passed, 0 failed. JS syntax и JSON configuration PASS.
В Cloudflare runtime тест не выполнялся; Node не доказывает соблюдение CPU budget
конкретного тарифа. Необходимо подтвердить в реальных scheduled executions.
Пакеты/runtime/dependencies Aura, стратегия, risk policy, портфели и workflow
не менялись. Code/security review: fixed destination, no redirects, bounded
response/retries, secret binding only, no public trigger, explicit failed contract.

Production smoke: повтор job 116524305322 run #15 завершился SUCCESS.
Результат подтверждён по безопасной строке scheduler log; это ручной повтор,
не доказательство автоматической доставки Cloudflare/GitHub schedule.

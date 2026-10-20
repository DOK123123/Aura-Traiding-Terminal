# Aura 4.3 Bitget — Render Cron и альтернативный worker

## Выбор и стоимость

Основной вариант — **Render Cron Job**, который каждые пять минут выполняет
`python -u -m scripts.active43_render_scheduler --once`. Процесс напрямую вызывает
существующий `app.active43.service.Service.tick()` и завершается. Это тот же
controller, стратегия, Paper Engine, SQL commit и журнал, что используются HTTP
`/api/active43/tick`. Ни HTTP к спящему web, ни GitHub schedule не требуются.
Нового торгового движка, private API Bitget или метода ручного сигнала нет.

| Вариант | Дополнительные расходы | Ограничения |
| --- | --- | --- |
| **Render Cron → controller напрямую** | **От $1/месяц**, минимум за сервис; сверх минимума — активное время | Выбран: не зависит от web/GitHub, Render гарантирует один активный run одного cron |
| Render Background Worker → controller напрямую | Около **$7/месяц** за минимальный постоянно работающий instance | Готовая альтернатива, собственный serial timer, более высокая фиксированная база |
| Внешний HTTP cron → Render API | Зависит от провайдера; бывают бесплатные квоты | Зависимость от стороннего сервиса, сна/лимитов free web и холодного старта |
| Цикл внутри free web | $0 сверх квот | Не выбран: процесс может заснуть/перезапуститься |

Тарифы проверены 2026-10-20 по [Render pricing](https://render.com/pricing),
[cron billing](https://render.com/docs/cronjobs),
[background workers](https://render.com/docs/background-workers) и
[free limits](https://render.com/docs/free). Минимальный cron compute указан как
$0.00016/минуту, биллинг пропорционален секундам, минимум $1/месяц за сервис.
При 8640 запусках за 30 дней и среднем оплачиваемом времени 10 секунд получается
около $0.23, поэтому применяется минимум $1; при 60 секундах — около $1.38.
Реальное время запуска/работы и итоговую стоимость нужно измерить в Render.
Это не фиксированная цена $1: налоги, дополнительный traffic/build usage, тариф
workspace и ресурсы Supabase считаются отдельно. Бесплатного cron/worker Render
нет. Новый платный workspace, Redis, база, диск и платный LLM не требуются.

Web-интерфейс может остаться бесплатным и просыпаться по запросу владельца —
торговый процесс от него не зависит. Для постоянно доступного интерфейса и
аварийной кнопки без холодного старта paid web — отдельные примерно $7/месяц.
Полной непрерывности при сбоях провайдеров не гарантирует ни один из вариантов.

## Что установлено о текущем размещении

В репозитории `Procfile` содержит `web: python start_web.py`, а `start_web.py`
запускает FastAPI/uvicorn. По текущей конфигурации проекта это web-процесс;
в репозитории до этого PR нет отдельной конфигурации Render worker/cron.
Текущий торговый scheduler — внешний GitHub workflow с авторизованным HTTP-вызовом.
Недоставка GitHub `schedule` не означает неисправность движка и не препятствует
замене источника запусков. Доступа к Render management API/Dashboard в этой сессии
нет: точный instance plan, region, количество сервисов и биллинг существующего
аккаунта независимо не прочитаны. Рабочий web не переносится и не перенастраивается.

Free web засыпает после 15 минут без входящего трафика; холодный старт занимает
примерно минуту. Есть общие 750 free instance-hours в месяц и другие квоты. Worker
не использует запросы keep-alive для обхода этих ограничений. Фоновый процесс на
платном worker — штатная архитектура Render; у него нет бесплатного instance.

## Код и защита

- `scripts/active43_render_scheduler.py` — отдельная точка запуска, не импортируется web lifespan.
- По умолчанию `AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED` отсутствует/false: только
  `IDLE/WORKER_DISABLED` в логах, без market/DB clients, ticks, инициализации и сделок.
- Только точное `true` разрешает worker ticks. Это **не START PAPER**: сохранённые
  OFF/ON/PAUSED/EMERGENCY берутся из Supabase. OFF не открывает новые позиции.
- Worker сначала проверяет наличие существующего счёта через read-only `peek`.
  Отсутствующий счёт блокирует tick; `initialize`, reset, START и control не вызываются.
- В основном Cron-режиме **обязателен `--once`**: одна попытка tick, затем выход.
  Render задаёт UTC минуты **02,07,12,…,57**, как прежний cron, и не запускает
  вторую копию того же Cron Job параллельно. Ручной Trigger Run отменяет активный
  run: во время работающего tick его не нажимать. В альтернативном paid worker
  без `--once` есть startup tick и последовательный UTC timer без catch-up пачки.
- Частота не зависит от UI, браузера, компьютера владельца или GitHub Actions.
- Внутри одного Cron Job наложений нет по правилу Render; в worker вызовы последовательны. Между worker, API, старым GitHub runner и экземплярами
  во время deploy действуют существующие CAS revision, уникальный 5-минутный key и
  атомарный SQL state/events. Это защита финансовых записей; лишние параллельные
  чтения рынка теоретически возможны. После перехода GitHub расписание надо выключить.
- `SIGTERM/SIGINT` прекращает будущие запуски после текущего tick и закрывает clients.
  Альтернативный worker Blueprint задаёт grace 90 секунд против 50-секундного бюджета controller и
  12-секундного предварительного чтения. При принудительном kill безопасность
  обеспечивают транзакция, повторное чтение и идемпотентность; потеря ответа не
  является разрешением создать второй OPEN/CLOSE.
- При ошибке рынка сохраняется существующий PAUSED/recovery; при ошибке БД нельзя
  подтвердить переход/открытие. Новые входы блокируются существующими проверками
  source/time/candle/contract/risk/SQL freshness. Риск 0,5%, день 2%, одна позиция,
  номинал ≤2000 USDT, комиссии и проскальзывание не меняются.
- Worker не содержит server endpoint, HTTP control, приватных биржевых методов,
  API-ключей биржи или fallback на иной счёт/источник.

Сохранённый ON после рестарта остаётся ON по существующей политике; worker не
выключает и не включает его сам. Потерянные свечи обрабатываются по существующим
правилам защиты позиций, без ретроспективных входов или будущих данных.

## Heartbeat и ошибки

Логи worker — JSON с UTC timestamp, компонентом и событиями `IDLE`, `WAITING`,
`TICK_SAVED`, `ERROR`, `STOPPED`. Коды ошибок — allowlist; значения env, DSN, токены,
сырые ответы/исключения и полные портфели не выводятся. `WAITING/IDLE` — только
живость процесса, **не** подтверждённый финансовый heartbeat.

`TICK_SAVED` подтверждается ответом существующего controller после commit и
проверки immutable receipt; PAUSED печатается как PAUSED, а не успешная торговля.
В Supabase существующий TICK/ERROR журнал и `last_run_at`/`last_successful_run_at`
сохраняются тем же кодом. При недоступной БД ERROR остаётся в логах Render: обещать
его запись в недоступную БД нельзя. Следующая попытка идёт в следующем слоте,
без бесконечного быстрого retry. Ошибка не переводит Paper в ON.

Owner UI читает тот же счёт/позицию/PnL и видит heartbeat worker. Локальный cache
свечей web и worker не разделяется: web-график может оставаться пустым после сна
до собственного получения данных; позиции и бухгалтерия от этого не теряются.
Кнопка диагностики также проверяет конфигурацию HTTP scheduler token веб-сервиса;
его существующее значение не менять, хотя сам worker HTTP-токен не использует.

## Подготовка владельцем после review и Merge

**Ничего ниже не выполнено автоматически. Создание Cron Job платное.**

1. В [Render Dashboard](https://dashboard.render.com/) выбрать **New → Cron Job**,
   подключить репозиторий и `main` после Merge. Имя `aura-active43-bitget-paper-cron`,
   минимальный instance Starter / 0.5 CPU / 512 MiB. Выбрать регион существующего web,
   где подтверждён Bitget. Build: `pip install -r requirements.txt`. Command:
   `python -u -m scripts.active43_render_scheduler --once`. Schedule:
   `2-59/5 * * * *` (UTC). Auto-Deploy OFF.
2. Для Cron задать следующие env, используя текущие Supabase значения приватно
   через Render Environment/группу, без пересылки ключей в чат/коммиты:

   | Переменная | Значение/источник |
   | --- | --- |
   | `AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED` | **false**, до проверки и разрешения |
   | `AURA_ACTIVE43_BITGET_ENABLED` | true — доступность модуля, не ON торговли |
   | `AURA_ACTIVE43_BITGET_SUPABASE_URL` | тот же URL текущего Active43 Bitget счёта |
   | `AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY` | существующий service-role key, только private env |

   Если используется общий `AURA_ACTIVE43_ENABLED` kill switch — согласовать его
   значение и в Cron. Env разных сервисов не синхронизируются автоматически.
   **Серверный env kill switch только на web не останавливает отдельный Cron/worker.**
   Общий запрет входов — сохранённый STOP/EMERGENCY в Supabase. Новому процессу не
   нужны owner password, scheduler token, ключи Bitget или секреты Aura 4.2.
3. Deploy нового Cron с флагом false: ожидается `WORKER_DISABLED` и завершение
   процесса, без доступа к БД. Web Render не требуется redeploy. Альтернатива
   ручным полям — отдельный Blueprint `deploy/render-active43-cron.yaml`, после
   проверки стоимости/уникального имени. Файл не корневой `render.yaml` и сам
   ничего не создаёт. Начальный deploy возможен даже при autoDeploy OFF.

Официальная JSON schema проверена локально. Management API/provisioning не
проверены без доступа к Render. Валидная схема не доказывает deploy. Не создавать
второй Cron Job с тем же назначением.

Для альтернативного постоянно работающего worker готов отдельный
`deploy/render-active43-worker.yaml`: тип worker, команда без `--once`, один
instance, shutdown delay 90 секунд, флаг false. **Выбрать один вариант**, не
применять оба Blueprint. Оплата worker около $7/месяц. Оба используют один runner
и существующий счёт, но двойные scheduler дадут лишние чтения даже при SQL-дедупликации.

## Проверка и включение — отдельно от установки

После отдельного разрешения владельца:

1. Подтвердить PAPER **OFF** в Owner Panel, баланс/позиции/историю не менять.
   Выключить только GitHub `AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED=false` для Aura 4.3,
   оставив Aura 4.2 workflow без изменений. Убедиться, что нет исполняющегося старого
   tick; отмена HTTP-клиента не доказывает отмену серверного commit.
2. Установить в **Cron Job** `AURA_ACTIVE43_BITGET_RENDER_SCHEDULER_ENABLED=true` и применить
   изменение/новый deploy артефакта Cron. Это отдельно разрешает scheduler, но не торговлю.
   Проверить два последовательных **scheduled** `TICK_SAVED` примерно через 5 минут,
   mode OFF, opened=closed=0, Supabase readback и свежий `last_successful_run_at`.
   Доступ Bitget из нового worker подтверждается только при его настоящем анализе;
   успешный OFF heartbeat сам рынок не запрашивает.
3. После успешной проверки и отдельного согласия на PAPER нажать
   **START EXPERIMENTAL PAPER** в существующей Owner Panel. Ждать естественных
   SIGNAL → OPEN → UPDATE → CLOSE; проверять journal и баланс/комиссии.
   Нативный worker fetch/анализ Bitget и natural OPEN/CLOSE ещё требуют подтверждения.
   Закрыть браузер; контролировать сохранённые timestamps, а не локальную страницу.

Для одного разрешённого tick: `python -u -m scripts.active43_render_scheduler --once`,
также требует Render scheduler flag true; режим счёта не меняет. Не запускать на production
как тест OPEN/CLOSE. Готовность 24/7 оценивается наблюдением минимум 24–48 часов:
нет пропусков/старых heartbeat, корректны restart/recovery, нет дублей, ограничения
CPU/RAM/сети не превышены. Разовое успешное выполнение этого не доказывает.

## Аварийное отключение и rollback

- Owner **STOP** сохраняет OFF и отменяет pending. **EMERGENCY STOP** сохраняет
  постоянный запрет входов; автоматически не снимается. Worker продолжает защитные
  выходы существующей позиции. Не отключать worker при открытой позиции как замену SL/TP.
- После отсутствия позиции и pending можно установить Render scheduler flag false или
  приостановить worker в Render. Env-изменение останавливает будущие тики только
  после применения/restart; уже идущий commit может завершиться.
- При недоступной Supabase нельзя считать owner STOP сохранённым. Приостановка
  worker останавливает будущую обработку, включая виртуальные SL/TP; это не CLOSE.
  До восстановления провайдеров непрерывная защита виртуальной позиции не гарантирована.
- Для rollback: сначала сохранить STOP/EMERGENCY, дождаться защитного завершения
  позиции, выключить worker. Можно вернуть GitHub scheduler после явного решения,
  но его прежняя недоставка расписания этим не устраняется. Никаких SQL reset,
  удалений истории или переинициализаций счёта.

## Итог проверок

**1532 Python passed, 2 skipped; 208 JavaScript passed.** Новые 19 проверок runner
прошли; Active43 PostgreSQL выполнен: 13 групп проверок, 7 сценариев исполнения,
2 native CLI/HTTP и 2 native Render-runner LONG/SHORT цикла. Две пропущенные проверки —
отдельные opt-in PostgreSQL suites старых Auto42/Practice. Есть одно существующее
Starlette/AnyIO deprecation warning. Версии пакетов совпадают с requirements.txt.
Оба Blueprint валидны по официальной JSON Schema Render; Python syntax/app import
и diff checks выполнены. Доказательства: `AURA43_RENDER_SCHEDULER_RESULTS.json`.

CODE_READY=TRUE, PAPER_ONLY=TRUE, PRODUCTION_READY=FALSE,
RENDER_SCHEDULE_VERIFIED=FALSE. Готовность кода не равна работающему 24/7 deployment.

## Изолированные проверки и пределы доказательств

Тесты worker проверяют OFF, LONG/SHORT, SL/TP, независимую математику комиссии/PnL,
конкурентные тики, restart, отсутствие счёта, outage/recovery, последовательный
таймер без catch-up и graceful stop. PostgreSQL runner дополнен двумя полными
native Bitget-fixture LONG/SHORT циклами через worker, реальный engine и настоящие
локальные SQL RPC, без web tick. Также сохраняются CLI/HTTP циклы и существующие
SQL/RLS/legacy-account проверки. Все тестовые OHLCV/сделки только в isolated БД.

В этой работе нет production тиков, создания платных ресурсов, изменения ключей,
разрешения ON, merge или deploy. Нет management доступа для подтверждения тарифа
и состояния Render worker. На Render не проверены: provisioning, доступ Bitget и
Supabase именно нового worker, periodic heartbeat, настоящий restart, 24/7 и
естественный автономный OPEN/CLOSE. Система получает проверенный **механизм**, а
не неподтверждённый статус круглосуточной эксплуатации. SQL-миграций нет.

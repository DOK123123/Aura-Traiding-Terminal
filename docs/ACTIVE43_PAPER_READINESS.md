# Aura 4.3: единая read-only готовность PAPER

В Owner Panel перед прежним блоком Cloudflare off_only расположен открытый блок
**AURA 4.3 · Готовность автономного PAPER · только чтение** и кнопка
**ПРОВЕРИТЬ ГОТОВНОСТЬ PAPER**.

## Что делает кнопка

Owner-authenticated `GET /api/active43/paper-readiness`, без кеширования ответа:

- Дважды `Store.peek()` существующего счёта; никаких `load`, `adopt`, seed,
  initialize, tick, controls, mark/roll_day или записи. Несовпадение revision/state
  после сетевой проверки означает BLOCKED и необходимость повторить чтение.
- Отдельный `Market` с точной production-конфигурацией SR_BOUNCE 5m. Те же публичные
  Bitget USDT-M Futures BTCUSDT endpoints, часы/свежесть, контрактные фильтры,
  непрерывная закрытая история >=1000 свечей и тот же анализ. Не использует
  stale cache рабочего движка и не меняет service.config или watermark.
- Отображает UTC открытия/закрытия последней свечи, UTC получения, возраст после
  закрытия, длительность запроса и полноту окна. Показывает именно preview текущей
  закрытой свечи, последнее сохранённое направление сигнала и сохранённое решение.
  AUTO_OFF не затирает BOUNCE_NO_CONFIRMED_REJECTION и другие причины стратегии.
- Читает до 100 последних событий через существующий SELECT-only history RPC,
  проверяющий envelope SHA256, scope и epoch. Это HTTP POST к read-only SQL-функции,
  не запись БД. Новые SQL, таблицы, grants и платные сервисы не нужны.
- READY требует OFF/пустой счёт/нет pending/нет recovery, production risk PASS,
  выбранную SR_BOUNCE 5m, свежий полный снимок рынка и две соседние свежие
  scheduled-квитанции текущего epoch с разными tick/invocation ID. Отсутствие
  торгового сигнала не является блокером технической готовности.

READY означает готовность **к отдельно разрешённому запуску**, а не ON,
прибыльность или PRODUCTION_PAPER_VERIFIED. Ответ явно сохраняет последнее false.
При ON/PAUSED/EMERGENCY это стартовый checklist BLOCKED, а не диагноз поломки.
Возраст ответа ограничен 60 секундами; переход новой 5m-границы также гасит READY.

## Доказательства автоматического scheduler

Предыдущий Worker не сохранял источник вызова в БД. Его квитанции не становятся
автоматическими задним числом и не дают READY.

Новая версия **существующего** Worker передаёт `X-Aura-Scheduled-At` только из
scheduled handler. Уже существующий application invocation ID сохраняется вместе
с UTC расписания и итогом обработки в **том же атомарном TICK event**, без новой
записи/таблицы и без изменения финансового состояния. Сервер проверяет форму,
Cron-фазу (:02/:07/... UTC), допустимую задержку и scheduler auth. Отсутствующий
заголовок допускается для совместимости, но означает отсутствие доказательства.
Некорректный заголовок отклоняется до tick. Дубликат не перезаписывает attribution.
Контекст изолирован между async запросами; повторные слоты не дают второй сделки.

Это **заявление авторизованного scheduler-клиента + фактическая неизменяемая
квитанция БД**, не криптографическая аттестация платформы Cloudflare. Владелец
scheduler secret технически может сформировать такие заголовки вручную.
Readiness не подключается к Cloudflare audit API и не утверждает, что Worker
получил HTTP200/TICK_SAVED: сохранять получение клиентом ответа до самого ответа
невозможно. Поля `cloudflare_audit_verified=false`, `http_delivery_verified=false`
сохраняют эту границу доказательств. Если нужна независимая платформенная
аттестация, необходим отдельный read-only доступ к Cloudflare logs; сейчас его нет.

Для PASS нужны два OFF/COMPLETED receipt, scheduled UTC с интервалом 300 секунд,
разные IDs, возраст последнего <=360 секунд и предыдущего <=660 секунд и подтверждённый scope/current epoch.
Сканирование ограничено 100 событиями; если нужные receipt вне окна, BLOCKED,
а не догадка. Успешное чтение старого cached status не заменяет эти условия.

## Совместимость и установка после отдельного разрешения

1. Merge/deploy backend и Owner UI. Старый Worker продолжает tick как раньше,
   но новый checklist будет BLOCKED по отсутствию scheduled evidence.
2. Обновить **только код** существующего `aura-ctive43-scheduler` из
   `deploy/active43-free-worker/worker.mjs`. Сохранить имя, secret, variables,
   `saved_mode`, enabled, routes и Cron. Не применять default wrangler config:
   у него другое имя и выключенные значения. Новая версия:
   `ACTIVE43_CF_READINESS_2026_10_24`.
3. Дождаться двух реальных автоматических OFF-слотов и нажать новую кнопку.
   Не выполнять ручной tick/START ради зелёного статуса. Если только heartbeat
   обновлялся ранее, новая кнопка отдельно проверяет рынок, даже при OFF.

Новый Worker -> backend PR32 совместим: старый backend игнорирует дополнительный
заголовок, но не сохраняет attribution. Новый backend -> старый Worker совместим:
отсутствие заголовка не блокирует tick. Ни один вариант не создаёт новые ключи,
не меняет trading logic, risk, комиссию, SL/TP или параметры Bounce/Donchian.
После обновления ожидается не более одного probe на web-process; конкурентное
нажатие получает READINESS_BUSY без ожидания trading lock. Probe ограничен 45с;
CPU-анализ вынесен существующим run_in_slot из event loop. Автоматического polling
рынка этой кнопкой нет. Дополнительные API вызовы — только по нажатию владельца.

## Проверки и review

Новые offline тесты: owner auth/no-store; запрет load/commit/tick/control;
сохранность счёта, config, revision и событий; реальные Bounce preview;
старые/ручные/дублированные/malformed receipt; stale/clock/API/incomplete candles;
concurrent read и ограничения ресурсов; persisted attribution/restart/duplicate;
malformed metadata/auth; frontend contract/expiry/XSS/единственный GET.
Настоящий локальный PostgreSQL harness дополнительно сопоставляет две реальные
Worker -> loopback HTTP -> Store -> SQL квитанции с ответом readiness и сравнивает
весь account/events ledger до/после чтения побайтово. Это не hosted Supabase.
Локальный Chromium проверяет кнопку и то, что ON-ledger остаётся неизменным при
BLOCKED. У production Render/Worker ничего автоматически не публикуется.

Code/security review: owner dependency до любых чтений; whitelisted payload,
только публичный фиксированный Bitget client; отсутствие произвольного URL;
read-only peek/history; атомарная attribution внутри прежнего TICK; никаких
дополнительных исполнений; JS textContent; no-store/redirect:error/time budget;
отдельный mutex probe, без захвата торгового lock. Параметры/стратегии/SQL/Aura4.2/
Practice не изменены. Остаточные риски: доверие scheduler token, нет независимого
Cloudflare audit, snapshot может быстро устареть, ограничения бесплатного Render,
свечная виртуальная модель исполнения и funding по-прежнему не моделируются.

# Aura 4.3 Cloudflare Cron: диагностика доставки

## Доказанная причина в коде и границы production-аудита

В main `cf955c4` Worker после успешного HTTP 200 и проверки полного read-only
контракта сам выбрасывал `Error('DIAGNOSTICS_BLOCKED')`, если сервер возвращал
status=BLOCKED. Исключение попадало в catch, записывалось как REQUEST_FAILED и
пробрасывалось из scheduled handler. Такое поведение воспроизводимо и приводило
к outcome exception при **успешной доставке** блокирующего результата.
Это не доказательство причины конкретного события владельца: доступа к trace,
bindings, Cron expression и версии опубликованного Cloudflare Worker нет.
Возможный UNEXPECTED_CRON, ошибка секретов/авторизации, сети либо превышение
CPU без этих данных не подтверждены. Исправления настроек наугад не выполнялись.

Сервер уже корректно возвращает HTTP 200 для валидного результата PASS/BLOCKED
через POST `/api/active43/diagnostics/scheduler`. HTTP 401/503 от auth, ошибки RPC
и проверки состояния не заменяются PASS. Серверные endpoints не меняются.

## Новое поведение

| event | Значение |
| --- | --- |
| DISABLED | Cron выключен в binding; ни одного HTTP-запроса |
| CONFIG_ERROR | Неверная операция, отсутствующий/некорректный secret, просроченный trigger или несовпадающий Cron; HTTP не выполняется |
| RENDER_REACHED | Получен HTTP-ответ, включая 401/403/5xx; это ещё не подтверждение авторизации или контракта |
| DIAGNOSTICS_RECEIVED | HTTP 200 и все существующие проверки read-only/identity/safety пройдены |
| DIAGNOSTICS_BLOCKED | Диагностика доставлена, status=BLOCKED; нормальное завершение handler, торговая готовность не подтверждена |
| REQUEST_FAILED | Сеть, timeout, HTTP-ошибка, неверный контракт либо отказ выполнения tick; исключение сохраняется |
| TICK_SAVED | Проверен сохранённый ответ existing tick; учитывать status, operation и mode |

Каждая запись содержит operation, attempt, http_status, code и фиксированную
paper-only identity. Для событий до HTTP attempt=0 и http_status=null.
Невалидная операция не печатается (operation=null). Raw body, headers, exception
messages, токены, суммы, position ID и URL Supabase не логируются.
DIAGNOSTICS_RECEIVED дополнительно содержит только статусы Bitget/Supabase/scheduler,
их коды из allowlist и supabase_stage из фиксированного списка. Неизвестный код
становится UNCLASSIFIED_SERVER_ERROR; неизвестный stage — null.

Внешние пробелы в secret отклоняются как CONFIG_ERROR: Fetch нормализует HTTP
header, а сервер сравнивает сохранённый токен буквально. Секрет не исправляется
и не заменяется автоматически; значение не выводится. Это защита конфигурации,
а не утверждение, что пробелы присутствуют у владельца.

Ошибки 401/403 и redirects завершаются без повторов. Bounded retry, Retry-After,
бюджет/таймауты, 32 KiB response limit, scope/source, risk guards, OFF-only checks
и saved_mode сохранены. PAUSED tick по-прежнему не объявляется здоровым/COMPLETED
и не повторяется немедленно. Для diagnostics только валидный BLOCKED перестал
быть исключением; неверный read_only/state_changed/scope остаётся INVALID_CONTRACT.

## Workers Free и Cron

Перепроверено 22 октября 2026 по официальному исходнику документации Cloudflare:

- [Limits](https://developers.cloudflare.com/workers/platform/limits/),
  [официальный исходник](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers/platform/limits.mdx).
- [Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/).
- [Scheduled handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/).

Free: 10 ms CPU на вызов Cron, 15 min wall time, 50 subrequests, 128 MB RAM,
100000 requests/day, 5 Cron triggers/account. Ожидание fetch не расходует CPU.
В этой реализации максимум два запроса, до 120 s на попытку включая тело,
до 240 s общего бюджета (сокращается для позднего trigger), 32 KiB на ответ.
На сервере выполняются тяжёлые проверки; Worker не запускает backtest/engine.
Новые зависимости или Node APIs в Worker не добавлены.

`2-59/5 * * * *` — пять полей, шаг 5 минут со второй минуты, UTC, 288 событий/сутки.
Handler намеренно требует точного совпадения с CRON; `*/5 * * * *` и `* * * * *`
не эквивалентны его конфигурации. Несовпадение теперь явно выдаёт
CONFIG_ERROR/UNEXPECTED_CRON с expected_cron. Default bindings остаются false/diagnostics.
Async scheduled handler с await поддерживается; отсутствие ctx.waitUntil не является
ошибкой для одной awaited задачи. Реальный workerd/Cloudflare CPU в этой среде
не измерен: наличие Node-тестов не доказывает соблюдение 10 ms на production.
Платные планы и лимиты CPU не менялись. При exceededCpu нужен реальный trace;
переходить на платный план автоматически запрещено.

## Владельцу после Merge (без новых ресурсов)

1. Cloudflare Dashboard → Workers & Pages → **существующий aura-active43-scheduler**
   → Edit code. Опубликовать новый `worker.mjs` из main **в этот Worker**.
   Render deploy, SQL и новые секреты для этого исправления не нужны. Не менять
   PAPER/режим операции/флаг Cron при обновлении кода; не создавать Worker из шаблона.
2. Открыть Observability → Logs, отфильтровать component=ACTIVE43_FREE_SCHEDULER.
   При отдельно разрешённом diagnostic Cron ожидаются RENDER_REACHED (200),
   DIAGNOSTICS_RECEIVED и, если есть блокировка, DIAGNOSTICS_BLOCKED без REQUEST_FAILED.
   Последний событие не разрешает PAPER. Если CONFIG_ERROR, использовать его code:
   UNEXPECTED_CRON — сравнить trigger с `2-59/5 * * * *`;
   SCHEDULER_NOT_CONFIGURED — проверить существующий Secret binding без публикации
   значения. SCHEDULER_TOKEN_MISMATCH/HTTP_UNAUTHORIZED — сравнить существующий
   binding с Render приватно; не генерировать новые ключи без необходимости.
3. **Только после отдельного разрешения проверки off_only** и подтверждения
   read-only Owner Panel (PAPER OFF, ноль позиций/pending/pending_exit, guards PASS)
   владелец выбирает operation=off_only. Cron включается владельцем только при
   отдельном разрешении; эта работа его не включает. Дождаться двух разных
   автоматических Scheduled invocation, минимум через один пятиминутный интервал.
   В обоих должны быть RENDER_REACHED/200 и TICK_SAVED, operation=off_only,
   status=COMPLETED, mode=OFF, opened=closed=0, state_saved=true. Проверить свежесть
   последнего успешного tick через read-only диагностику. Retry/duplicate внутри
   одного invocation или ручной тест не заменяют два автоматических события.

Не выполнять START/STOP/RESET/initialize ради этой проверки. При ошибке не пытаться
включить PAPER. Изменения Cron могут распространяться до 15 минут; не объявлять
успех до двух настоящих Scheduled. Эти два события проверяют OFF heartbeat и
сохранение, а не естественный торговый OPEN → CLOSE.

## Проверки и review

Новые регрессии: BLOCKED не бросает исключение; auth/network/contract остаются
ошибками; safe log fields и no-secret leakage; выключенный Worker не делает HTTP;
неверный Cron логируется; off_only/saved_mode и две изолированные OFF-доставки.
Существующий серверный HTTP endpoint также формирует реальные PASS/BLOCKED
ответы (fresh/stale/missing account) для проверки через Node Worker. HTTP/рынок/
хранилище изолированы и не подключены к production.

Code review: минимальные изменения транспортной диагностики; проверки identity,
сохранения и OFF-only не ослаблены. Security review: фиксированные host/path/header,
redirect manual, allowlist логов, нет новых публичных endpoint, ресурсов или прав.
Aura 4.2/Practice/engine/SQL/баланс/позиции не менялись. Критических/high замечаний
не найдено. Остаточные риски — реальные Free CPU, конфигурация/версия Worker,
cold start Render и best-effort доступность инфраструктуры.

CLOUDFLARE_OFF_ONLY_CYCLES_VERIFIED = FALSE

PRODUCTION_PAPER_VERIFIED = FALSE

Причина: два настоящих scheduled off_only в Cloudflare в этой задаче не запускались
и их логи недоступны. Merge, Deploy и production configuration changes не выполнялись.

Результаты ветки: **1560 Python passed, 2 skipped**, 192,27 s; **233 JavaScript
passed**, включая 21 Worker-тест. Три новые Python HTTP → Worker проверки
fresh/stale/missing account прошли. Полный Python запуск включал настоящий локальный
PostgreSQL (`AURA_ACTIVE43_VERIFY_POSTGRES=true`): 13 групп проверок, 7 сценариев,
RLS и restart PASS. Два skip — существующие opt-in suites Auto42/Practice;
одно существующее предупреждение Starlette/anyio. AST 231 Python-файла,
import app.main, node --check и git diff --check — PASS.

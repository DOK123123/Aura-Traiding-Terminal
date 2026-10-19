> АРХИВ V2 BYBIT (PR #15). Текущий v3 использует отдельный Bitget namespace, env и scheduler header. Не применять эту инструкцию для нового портфеля. См. [v3 Bitget](AURA43_BITGET_OPERATIONS.md).

# Aura 4.3 Active Paper — Bybit Futures: эксплуатация и проверка

Сборка `AURA_4.3_ACTIVE_PAPER_2`, отдельный BTCUSDT USDT Perpetual PAPER-портфель.
Режим выключен по умолчанию. Реальные ордера, account/private Bybit API,
Demo funds и реальные деньги не используются. Aura 4.2, Paper Practice и их
scheduler/данные не переключаются и не сбрасываются.

**PRODUCTION_READY = FALSE до проверок на Render.** Изолированные проверки
подтверждают технический execution, но не доступ Bybit из региона Render,
Supabase PostgREST/JWT, установленные env, uptime или реальные сделки сервера.
В текущем проверочном окружении публичный Bybit возвращает региональный 403.
Это блокирующий доступ, а не отсутствие сигнала. Не обходить запрет, не заменять
источник Spot, не включать входы без успешного preflight.

## Что проверено в архитектуре

Main `0e7a721220d9f76af1f841305f344163a048b4f9`, PR #15 открыт, не merged.
Доработки продолжают ту же ветку PR #15. Research PR #3–#11 не интегрируются.
В PR #15 работали Decimal engine, CAS/SQL, risk, causal next-open и owner UI,
но Active43 и его отдельная текущая котировка использовали Binance Spot.
Переход на Bybit без замены обоих адаптеров смешал бы источники PnL/анализа.
В прежней панели не было явной оценки свежести scheduler и Futures-графика.
Также исправлены привязка краткого analysis cache к конфигу и часам, контролируемая
ошибка нормализации свечей, изоляция 5m от старого preview и проверка source/version
в UI/scheduler. Архивные Spot CLI теперь отказываются считать данные текущим Bybit
core и не могут перезаписать новую selection. На эти случаи добавлены регрессии.

Новый путь:

`внешний cron → POST /api/active43/tick → Bybit V5 public GET → полное
закрытое окно → native Lab индикаторы/Donchian → pending signal → независимый
risk/size/lot/tick/cost gate → существующие Auto42 Decimal функции → отдельные
Bybit SQL RPC → readback → owner status/UI`.

Нет writer на биржу и нет ручного API OPEN/CLOSE/SIGNAL. `core.py` остаётся
network-free. `app.bybit_linear.Client` повторно используется с неизменным
официальным `https://api.bybit.com`, `category=linear`, `symbol=BTCUSDT` и
закрытым GET allowlist. Только public market kline/instruments-info/tickers.
Общий клиент сохраняет прежние интервалы 15m/1h/4h; подкласс Active43 отдельно
поддерживает сохранённый 5m. Его отдельный preview и read-only Demo-клиент не подключаются к исполнению.

## Стратегия и исполнение

Фиксированный Donchian 15m из PR #15, без подбора параметров:

- LONG: close выше максимума high **предыдущих** 20 закрытых свечей.
- SHORT: close ниже минимума low предыдущих 20 закрытых свечей.
- ATR14, исходный SL 2×ATR, TP 4×ATR. Стратегический выход по обратному
  каналу предыдущих 10 свечей. Параметры/индикаторные формулы сохранены.
- Сигнал фиксируется при закрытии свечи. Виртуальное исполнение на следующем
  open учитывается **после закрытия следующей свечи**. Это OHLC accounting,
  не мгновенное исполнение по живому тикеру и не реальная заявка на бирже.
- SL/TP работают по last-trade OHLC, не mark price. При двух касаниях — SL.
  Gap SL исполняется по неблагоприятному open; gap TP — по target, консервативно.
- Оценка PnL по свежему public last price — read-only, не исполняет стопы.
- 15m/1h/4h (и сохранённый 5m) доступны адаптеру и тестам, UTC alignment.
  Активный конфиг 15m; новый обязательный MTF-фильтр не вводится. Прежняя
  MTF-стратегия 4.2 не изменяется. Более старшие свечи не используются из будущего.
- Начальные 10000 USDT; не более одной позиции; notional ≤2000; риск включая
  комиссии/SL-slippage ≤0,5%; дневной loss stop 2%, drawdown stop 10%.
  Это запреты входов, а не гарантированный потолок фактического gap-убытка.
- Фиксированные консервативные комиссии 0,10% и slippage 0,05% **на сторону**.
  Это модель Paper, не утверждение о тарифе Bybit/VIP. Funding, liquidation,
  leverage, depth/latency не моделируются. PnL не выдаётся за futures-return с funding.
- Заморожены qtyStep/minQty=0.001 BTC, minNotional=5 USDT, tick=0.10 USDT.
  Реальный ответ instruments-info проверяется; отличие блокирует вход, не
  обновляет policy автоматически. При запрете/тайм-ауте metadata входов нет.
  Проверка maxMktOrderQty также обязательна. Lot округляется вниз, SL/TP
  приводятся к tick и затем заново проходят существующий риск-контроль.

`UNVALIDATED_FUTURES`: стратегия не признана прибыльной. Предыдущие Spot
результаты `NO_EDGE_FOUND` остаются явно помеченным архивом, не переносятся
в Futures-статистику и не являются основанием для оптимизации/активации.
Повторить старое исследование можно на коммите `6284a3c`, не текущим Bybit core.

## Перезапуск, пропуски и scheduler

ON/OFF, баланс, watermark, pending, позиция, idempotency keys и история — в SQL,
не в localStorage браузера. Перезагрузка страницы только читает status.
Новый процесс сначала читает/валидирует durable state; не создаёт второй счёт,
не сбрасывает ON/OFF и не перезапускает позицию из браузера.

Один scheduler Active43 — `.github/workflows/aura-active43.yml`, отдельная
concurrency group/token и заголовок `X-Aura-Active43-Bybit-Token`.
Старый Spot scheduler header не принимается; новый workflow не может случайно
запустить старый Spot runtime. Tick-ответ проверяется по Bybit source и версии v2. Он не запускается из UI и не добавляет второй
внутрипроцессный loop. Multi-instance защищён row lock/CAS и immutable tick ID
по epoch/5-minute bucket. Потерянный ответ — unknown outcome, не подтверждённый OPEN.
Повтор читает receipt; двойных entry/exit fees нет.

При сбое Bybit состояние PAUSED и причина сохраняются, если доступна БД.
На свежих данных восстанавливается только ранее вооружённый ON без risk stop.
STOP/EMERGENCY не самоснимаются. При недоступности SQL нет подтверждённого
исполнения; следующий процесс читает durable состояние. Риск-stop никогда
не снимается ради восстановления соединения.

После пропусков не открываются сделки по старым сигналам. Pending отменяется;
доступные закрытые свечи проверяют старые SL/TP, без выдуманных промежуточных
ATR trail. Окно ограничено примерно 1000–1288 свечами. Если watermark вышел
за окно или история изменилась, `SOURCE_CORRECTION_OR_HISTORY_MISSING` блокирует
цикл: требуется проверка владельца; отсутствующие цены не восстанавливаются
синтетически. До восстановления защита позиции не гарантируется.

Scheduler status: NOT_CONFIGURED / NEVER_SEEN / FRESH / STALE. FRESH означает
сохранённый tick не старше 360 секунд, а не отсутствие торговой ошибки.
UI отдельно показывает источник, отказ, успешные market-data timestamp и DB
readback. GitHub schedule best effort, бесплатный Render может спать. Остановка
сервера задерживает Paper SL/TP: на бирже нет страховочного стоп-ордера.
Работа 24/7 не подтверждена и на free-тарифе не обещается.

## Безопасная миграция Supabase

1. Создать backup существующих данных обычным способом владельца. Ничего не
   сбрасывать. Если прежний Spot Active43 уже запускался, перед сменой сборки
   запретить его входы и дождаться отсутствия позиции. Не оставлять старую Spot
   позицию без старого защитного scheduler. Программа не закрывает её автоматически.
2. Просмотреть **`scripts/active43_bybit_schema.sql`** и применить его в SQL Editor
   владельца Supabase. Это отдельные `aura_active43_bybit_account/events` и RPC.
   Весь файл в транзакции; повторное применение проверено. `active43_schema.sql`
   относится к архивному Spot и для нового режима не требуется.
3. Не менять старые `aura_auto42_*`, `aura_practice_*`, `aura_active43_*`.
   Новая миграция их не изменяет. Нужен pgcrypto в схеме extensions, как в старом
   контуре. Не переносить существующее extension между схемами автоматически.
4. RLS включён; anon/authenticated не имеют table/RPC доступа. Только серверный
   service_role выполняет новые RPC. Этот проектный ключ широких прав — namespace
   не заменяет отдельный DB principal; ключ никогда не попадает в UI/Actions.
5. Проверить новые RPC в API schema cache (SQL делает NOTIFY pgrst).

Никаких новых платных ресурсов не требуется для самого кода. Исследований в
web-процессе нет. Текущие квоты Supabase/Actions и plan Render доступны только
владельцу; их остаток здесь не проверен. Append-only journal растёт на каждом
5-minute tick, даже без сделок. На свободном плане нужен контроль размера
таблиц/индексов и backup; автоматическое удаление истории не добавлено.

## Render: точные ручные действия

Доступа к Render API/управлению сервисом и production DB в этой работе нет.
Выполнено только публичное read-only `/api/health`. Никакой deploy не запущен.

1. Review PR #15, проверить тесты/SQL/источник. Учесть auto-deploy на merge;
   проверить его настройки **до** объединения. Ни merge, ни включение тут не делались.
2. Сохранить существующий `python start_web.py`, `PORT`, owner password,
   trading env и scheduler Auto42. Python dependencies не изменены. Сервис слушает
   `0.0.0.0:$PORT`, один uvicorn worker; несколько экземпляров безопасно используют CAS.
3. Новые/существующие отдельные env Active43:

   | Переменная | Значение/назначение |
   |---|---|
   | `AURA_ACTIVE43_ENABLED` | `true` — включает модуль, не торговый ON |
   | `AURA_ACTIVE43_BYBIT_ENABLED` | `true` — отдельное явное согласие на Bybit source; без него модуль не создаёт DB/market clients |
   | `AURA_ACTIVE43_SUPABASE_URL` | HTTPS URL проекта, server only |
   | `AURA_ACTIVE43_SUPABASE_SERVICE_KEY` | server service_role, не anon key |
   | `AURA_ACTIVE43_SCHEDULER_SECRET` | отдельный случайный printable ASCII token ≥32 символов, не owner/key/другой scheduler token |
   | `AURA_TESTNET_VIEW_PASSWORD` | существующий owner password, не менять |

   Bybit key/secret не нужны. `RENDER`/`RENDER_GIT_COMMIT` предоставляет Render;
   не подделывать их для получения VERIFIED. Нет env для Live/real execution.
4. Открыть `/api/health`, затем owner-вход `/api/paper/login` и отдельную панель
   **AURA 4.3 ACTIVE PAPER**. Первый новый счёт OFF/10000. Существующие торговые
   балансы/позиции должны остаться прежними. Прочитать SQL state и source.
5. Проверить доступ к `https://api.bybit.com` **из процесса Render**. При
   `REGION_OR_ACCESS_RESTRICTED` режим не запускать. Не использовать VPN,
   региональные зеркала, другой exchange или host override для обхода.
   Требуется разрешённая площадкой среда; тариф сам по себе не устраняет 403.
6. В GitHub добавить отдельный secret `AURA_ACTIVE43_SCHEDULER_SECRET` с тем же
   token и repository variable `AURA_ACTIVE43_SCHEDULER_ENABLED=true`. Workflow
   запускается вручную и примерно каждые 5 минут после попадания в default branch.
   Старые workflow/secrets не менять. Не считать наличие token доказательством cron.
7. Сначала `workflow_dispatch` и подтвердить FRESH/last_run_at при **OFF**, без
   позиции. Только затем владелец явно нажимает `START EXPERIMENTAL PAPER`.
   START не открывает сделку, а ставит свежую baseline и ждёт нового сигнала.
   Старые кнопки Start Paper/Auto42 управляют другими портфелями и не включают 4.3.
8. Закрыть браузер, дождаться нескольких внешних ticks. Проверить журнал и DB,
   затем перезапустить Render и проверить сохранённые mode/position/epoch/revision.
   Не ждать сигнал бесконечно: NO_SIGNAL — корректный результат. Техническая
   возможность OPEN/CLOSE уже проверена изолированными тестами.
9. Production подтверждается отдельно **только** естественной коррелированной
   цепочкой SIGNAL → OPEN → POSITION_UPDATE → CLOSE с Bybit source, одним
   position ID, Render SHA и SQL receipt. Отсутствие такого цикла не заменяется
   локальным TEST_ONLY и не отображается как VERIFIED.

## Проверка записей без изменения данных

```sql
SELECT revision, saved_at, payload::jsonb->>'market_source' AS source,
       payload::jsonb->>'mode' AS mode, payload::jsonb->>'balance' AS balance,
       payload::jsonb->'position' AS position,
       payload::jsonb->>'last_run_at' AS last_run_at,
       payload::jsonb->>'last_decision' AS decision
FROM public.aura_active43_bybit_account WHERE id=1;

SELECT seq, kind, created_at, payload::jsonb->'payload' AS event
FROM public.aura_active43_bybit_events
ORDER BY seq DESC LIMIT 100;

SELECT pg_size_pretty(pg_total_relation_size('public.aura_active43_bybit_events'));
```

Должны совпадать IDs, source, fees и balance с owner API. SQL таблицы используют
тот же `{payload,sha256}` envelope, что остальные контуры; не редактировать JSON
вручную. Изменённый checksum, scope или source блокирует controller.

Остановка: STOP запрещает входы, защитные выходы продолжаются. EMERGENCY
не снимается START. Не выключать feature/cron при открытой позиции: Paper-стопы
перестанут обрабатываться. Безопасный rollback — STOP, отсутствие позиции,
выключить только новый workflow/флаги, вернуть предыдущий SHA. БД/историю не
удалять и не конвертировать в Spot. Уровень drawdown 10% не сбрасывается API.

## Воспроизведение проверок

Все CLI отказываются работать при `RENDER`, не принимают production DSN/key.
PostgreSQL контейнер локальный, network=none, ports=0, 512MiB/1CPU. V5 market
fixtures синтетические **только в tests/scripts**, сигналы в двух native cycles
рассчитывает реальный Donchian, а не подставляет controller. DB настоящая;
Mock HTTP bridge ведёт к real SQL RPC, это не hosted PostgREST verification.

```bash
python -m pytest -q
node tests/test_active43_frontend.cjs
python -m scripts.verify_active43_postgres --output /tmp/aura43-bybit-pg.json
python -m scripts.verify_active43_browser --output /tmp/aura43-bybit-browser.json
```

Полный CI-like прогон с доступным локальным Docker:
`AURA_PRACTICE_VERIFY_POSTGRES=true AURA_AUTO42_VERIFY_POSTGRES=true
AURA_ACTIVE43_VERIFY_POSTGRES=true python -m pytest -q`.
В managed sandbox для тестов может понадобиться существующий test-only wrapper
`enable_sandbox_poll()` из `scripts/replay_aura_csv.py`; production loop не меняется.
Запустить также каждый `tests/*.cjs`, `node --check static/active43.js`, syntax/import
Python. При отсутствии Docker/Chromium пометить проверки NOT RUN, не PASS.

Финальные количества тестов, хэши текущих исходников, реальные локальные SQL
кейсы, mobile browser evidence, public probes, отдельные code/security reviews
и оставшиеся blockers: **`AURA43_BYBIT_VERIFICATION.json`**. Архивные
`AURA43_TECHNICAL_VERIFICATION.json`/`active43-research.json` относятся к старому
Spot-коммиту; их PASS не используется для текущей сборки.

## Code/security review и границы доказательств

Выполнены отдельные проходы проверки кода и безопасности по
`docs/ecc/TRADING_REVIEW.md` (self-review, не внешняя сертификация/не отдельные AI).
Проверены ingestion/UTC/closed/causality, ошибки нормализации, Decimal risk/cost,
source/config/epoch integrity, реальные SQL роли/rollback/CAS, unknown outcomes,
restart, owner/CSRF/token границы, XSS через textContent/SVG title, bounded
responses/CPU, GET allowlist и скан credential patterns только изменённых файлов.

Исправленные замечания: смешение Spot/Futures runtime; неверная привязка cache;
необработанный LabError; расширение общего preview API (исправлено без ослабления
старого теста); несогласованный источник quote; отсутствие проверки source/version
в ответах UI/scheduler; возможность запустить архивный Spot CSV новым core;
соответствие ATR stop шагу цены. Native indicator пороги не изменялись.

Неразрешённых critical/high **кодовых** замечаний после проверок не выявлено.
Отдельно остаются **release blockers**: непроверенный Bybit доступ из Render,
неприменённая владельцем production миграция/конфигурация, отсутствие deploy и
натурального Render/Supabase цикла. Региональный 403 текущей среды подтверждён;
он не доказывает результат запроса из другого сервера. Наличие service_role
секрета или PASS локальной БД не подтверждает hosted Supabase/PostgREST/JWT.
Новые платежи не выполнялись. Тариф, quotas и фактический uptime не проверены.

Полный pytest включает opt-in Auto42/Practice/Active43 local PostgreSQL tests.
В частности, два native LONG/SHORT цикла проходят **HTTP scheduler endpoint** с
новым Bybit header, без браузера, через реальные SQL RPC и owner status API.
Это технический PASS, а не реальная рыночная сделка и не production verification.

## Итог финального прогона

**1401 Python PASS**, 1 существующее предупреждение; **18 JavaScript suites PASS** (Active43 frontend: 16 tests). Реальная локальная PostgreSQL: 7 scenarios + 8 checks + 2 native HTTP cycles. Chromium mobile: PASS. Syntax/import: PASS. Production: BLOCKED/NOT TESTED по матрице machine report.

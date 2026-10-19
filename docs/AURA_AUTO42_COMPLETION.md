# Aura Auto Paper 4.2 — итоговая техническая проверка

Основа: `main` `9bd9fbbf1bf4fe42646af01d03dd6fdab16f9e70`, после PR #12/#13.
Research Lab и Draft PR #3–#11 не включены. Только виртуальный Auto42-портфель.
Эта ветка не выполняет merge, deploy, production tick, START или сделки.

## Реальный путь исполнения

1. GitHub Actions `.github/workflows/aura-auto42.yml` или отдельный
   `deploy/auto42-worker/worker.mjs` вызывает защищённый `/api/auto42/tick`.
   Браузер не является scheduler. Частота/секреты/конфигурация не изменены.
2. `app/automated/api.py:scheduler` проверяет отдельный серверный токен.
   Владелец управляет режимом через CSRF-защищённый `/control`; scheduler не
   может вызвать владельческие команды этим токеном.
3. `service.py:snapshot` → `market_data.py:snapshot_for_auto` → существующий
   `MarketContext`: публичные Binance Spot BTCUSDT, только закрытые 15m.
   Rolling-окно начинается на границе UTC 4h минус 4160 свечей; 1h/4h строятся
   только из полных закрытых блоков. Источник/хеш/время/прогрев проверяются.
4. `research/market_intelligence/structure.py:segment_states`: причинные
   подтверждённые pivots; breakout с буфером 0.1 ATR, retest до 8 свечей,
   касание в пределах 0.25 ATR и направленное закрытие. PR #13 сохраняет
   исходный setup до завершения/отмены. Будущие свечи его не подтверждают.
5. `strategy.py:_evaluate`: MTF 15m=1h=4h !=0, retest по тренду, ADX≥25,
   соответствующий regime, отсутствие встречной/неоднозначной liquidity,
   подтверждённый BOS/CHoCH исходного breakout, volatility 0.65…2,
   ATR/структурный SL и TP 2R, отсутствие встречного уровня до TP.
6. `engine.py:advance`: атомарно сохраняемый pending на закрытии сигнальной
   свечи. Заполнение по open **следующей** свечи учитывается после её закрытия;
   это существующая модель closed-candle Paper, не биржевой intrabar fill.
   Позиция может открыться и закрыться в одном таком расчёте.
7. `open_virtual`: Decimal, риск с комиссиями ≤0.5%, не более одной позиции,
   лимит notional 2000 USDT, дневной лимит 2%, drawdown 10%, баланс ≥0.
   Существующие commission 0.10% и adverse slippage 0.05% не изменены.
8. `protective/close_virtual`: SL/TP, неблагоприятный stop gap; TP gap
   консервативно по цели. При касании обоих уровней первым считается SL.
9. `service.py:_tick` → `storage.py:SupabaseStore.commit` → существующий
   `aura_auto42_commit`: row lock/CAS, уникальные события, состояние, watermark
   и ключ tick в одной транзакции. Ошибка записи не подтверждает OPEN.
   Неопределённый исход разрешается повторным чтением/идемпотентным ключом.
10. Следующий процесс читает тот же портфель из Supabase; существующий ON
    сохраняется. Retryable data error временно PAUSED; свежие данные позволяют
    восстановить только ранее включённый режим без срабатывания risk stop.

## Исправления

- **Защитное восстановление после >32 свечей.** Раньше `CATCHUP_LIMIT` навсегда
  оставлял открытый портфель на старом watermark даже при полной свежей истории.
  Теперь непрерывная валидная история позволяет закрыть/сопровождать существующую
  позицию. Пропущенные pending сбрасываются, задних входов нет. Ограничение для
  пустого портфеля сохранено; разрешён только свежий forward-сигнал.
- **Подтверждение собственного breakout.** Раньше retest мог заимствовать
  BOS/CHoCH от другого пробоя в пределах 8 свечей. Теперь направление, уровень
  и время `retest_origin` должны соответствовать подтверждённому исходному
  breakout. Это устраняет ложное подтверждение, а не ослабляет фильтр.
- **История.** Последние 60 произвольных событий могли не содержать ни одной
  CLOSE, хотя сделки были. Новый read-only RPC читает CLOSE отдельно, с epoch
  и курсором. Без его установки панель честно сообщает о частичной истории;
  торговый engine не зависит от этой миграции.
- **Панель.** Фактический последний SIGNAL, накопленные комиссии, PnL позиции
  с комиссиями входа/выхода, версия Render и отдельная свежая публичная котировка.
  Котировка не участвует в сигналах, marks или fills. Используется существующий
  фиксированный public-GET quote reader, без команд/хранилища Paper Practice.
  Старые ответы/котировки не отображаются как свежие.

`POLICY`, `PARAMETERS`, индикаторы, MTF, пороги, source, scheduler, SL/TP,
Paper Practice, существующие позиции/счета и торговые SQL RPC не изменены.
Новая проверка происхождения может только отклонить ранее ложное подтверждение.

## Что доказывают проверки

Машиночитаемые результаты и конкретные числа приведены в
`AURA_AUTO42_COMPLETION_EVIDENCE.json` и заключении ниже.

Локальный PostgreSQL 16: отдельная test DB в одноразовом контейнере, `network
none`, без портов/DSN/production-ключей, 512 MiB/1 CPU. Production Service,
engine и Store используются напрямую; только транспорт RPC заменён на psql.
Это настоящие SQL/транзакции/роли, но **не проверка HTTP PostgREST, Supabase
hosting, production Render или непрерывной работы внешнего scheduler**.

LONG/SHORT → SL/TP/оба уровня, mark, рестарт БД и контроллера, конкурирующие
контроллеры, повтор tick, отсутствие сигнала, stale/recovery, остановленная БД
и SQL failure после вставки событий проверяются изолированно. Независимый
Decimal oracle проверяет fill, fee rounding, slippage, PnL, итоговый баланс.
Синтетические контексты строго TEST_ONLY. Отдельный исторический цикл повторно
рассчитывает настоящий рыночный сигнал из закрытого rolling-префикса и проводит
его через Service/engine/локальные production SQL RPC. Он также не является LIVE.

Существующие тесты дополняются регрессиями оригинального breakout, LONG/SHORT,
8-свечного срока, будущих свечей, длительного protective catch-up, history flood,
авторизации новых GET, стоимости позиции и read-only UI.

## Воспроизведение локально

Не используйте production environment/ключи. Python зависимости — существующий
`requirements.txt`; дополнительные runtime-сервисы/платные API не нужны.

```sh
python -m scripts.download_auto42_history --end-date 2026-10-19 --output /tmp/btc-auto42.csv
python -m scripts.replay_auto42_verification --csv /tmp/btc-auto42.csv --output /tmp/replay.json --workers 2 --max-seconds 1500
python -m scripts.verify_auto42_postgres --output /tmp/auto42-postgres.json
# Для реального исторического сигнала из отчёта, не для production:
python -m scripts.verify_auto42_postgres --output /tmp/auto42-natural.json --history /tmp/btc-auto42.csv --signal-at 1784637900
python -m pytest -q
```

Имена output должны быть новыми. При исчерпании budget replay возобновляется
тем же вызовом по проверенному checkpoint. В облачном sandbox при необходимости
используется только test-wrapper `enable_sandbox_poll`; production loop не меняется.
Реальные архивы и полные equity/decision/checkpoint массивы не коммитятся.
Официальные URL, CHECKSUM и SHA256 CSV сохраняются в provenance рядом с CSV.

## Безопасный запуск владельцем на Render

1. Проверить итоговый PR, тесты и отсутствие конфликтов; merge выполняет только
   владелец. Если в Render включён auto-deploy, сначала учесть этот режим:
   само слияние может запустить deploy. В этой сессии ни merge, ни deploy нет.
2. Не сбрасывать счёт/позиции. Перед обслуживанием можно запретить **новые** входы
   штатным STOP, сохранив защитное сопровождение открытой позиции. Это действие
   выполняет владелец после проверки текущего портфеля.
3. Для полной истории выполнить **только** `scripts/auto42_trade_history.sql`
   в SQL Editor рабочей Supabase после просмотра SQL. Он добавляет индекс CLOSE
   и SELECT-only SECURITY DEFINER RPC, не обновляет/удаляет данные, не меняет
   существующие торговые RPC/таблицы/Practice. Browser роли EXECUTE не получают.
   Текущую `auto42_schema.sql` заново применять/сбрасывать не требуется.
4. Новые переменные не нужны. Сохранить существующие `AURA_AUTO42_SUPABASE_URL`,
   `AURA_AUTO42_SUPABASE_SERVICE_KEY`, `AURA_AUTO42_SCHEDULER_SECRET` и
   `AURA_TESTNET_VIEW_PASSWORD`; не копировать ключи в браузер/Git. На Render
   нельзя включать локальный SQLite вместо Supabase.
5. Владелец вручную развёртывает проверенный SHA. После рестарта: `/api/health`
   должен отвечать 200, неавторизованный `/api/auto42/status` — 401. После входа
   проверить Render SHA, реальный RPC CONNECTED, balance/position/revision,
   последнее сохранение и отсутствие неожиданных RESET/CONTROL/OPEN/CLOSE.
6. Если режим ранее OFF/PAUSED и нет риска/позиции, обновить панель и явно
   выполнить штатный START PAPER. Если уже ON, повторный START не нужен.
   `CATCHUP_LIMIT` у пустого портфеля требует owner START для свежего baseline;
   история/баланс не сбрасываются. При открытой позиции сначала успешный tick
   должен выполнить защитный catch-up; HISTORY_MISSING нельзя обходить.
7. Проверить **фактически** GitHub/Cloudflare triggers и интервалы accepted ticks
   в Supabase. GitHub cron — best effort, бесплатный Render может спать/холодно
   стартовать. HTTP health или один зелёный Actions run не доказывает 24/7.
   Никаких платных ресурсов эта ветка не создаёт. Необходимость платного
   always-on тарифа владелец решает отдельно по реальным пропускам/лимитам.
8. Закрыть браузер и наблюдать только штатные server ticks. Не менять фильтры,
   не создавать сигналы и не нажимать Practice ради подтверждения Auto42.
   При реальном сигнале должны последовательно сохраниться DECISION,
   pending → OPEN → POSITION_UPDATE → CLOSE_SL/CLOSE_TP с одним position ID,
   source/candle/run ID и балансом. Это может потребовать ожидания редкого setup.
9. Сверить результат через owner Live Monitor/journal и SQL SELECT ниже.
   Только matching настоящий Render/Supabase OPEN и CLOSE позволяют LIVE VERIFIED.
   При ошибке использовать STOP/EMERGENCY штатно; не RESET, не ручной SQL repair.

```sql
-- Только чтение. Не публикуйте содержимое своего частного портфеля.
SELECT revision,saved_at,
       payload::jsonb->>'mode' AS mode,
       payload::jsonb->>'balance' AS balance,
       payload::jsonb->>'realized_pnl' AS realized_pnl,
       payload::jsonb->'position' AS position
FROM public.aura_auto42_account WHERE id=1;

SELECT seq,kind,to_timestamp(created_at) AS event_utc,
       payload::jsonb->'payload' AS details
FROM public.aura_auto42_events
WHERE epoch=(SELECT payload::jsonb->>'epoch' FROM public.aura_auto42_account WHERE id=1)
  AND kind IN ('DECISION','OPEN','CLOSE','ERROR','LIVE_MONITOR')
ORDER BY seq DESC LIMIT 100;
```

Откат кода: предыдущий проверенный SHA через штатный Render rollback владельцем.
Не удалять историю или новые индексы/RPC: они read-only и совместимы со старым
кодом. При неизвестном исходе операции сначала прочитать состояние и журнал.

## Ограничения доказательств

Read-only public health и отсутствие обхода авторизации проверены. В этой
сессии нет production-владельческих credentials и доступа к приватным журналам.
Успешный Practice не доказывает strategy path: ручная команда обходит сигнальные
фильтры и использует отдельный портфель. `NO_CONFIRMED_SETUP` (подпись «Нет
подтверждённого retest») — нормальное отсутствие setup на конкретном cutoff,
а не свидетельство сломанной БД/engine. Кода `NO_CONFIRMED_RETEST` в main нет;
для точной привязки сообщения на Render нужно проверить SHA и сохранённое решение.

90 дней недостаточно для доказательства прибыльности/устойчивости редкой
стратегии. Отрицательный или положительный результат не меняет параметры.
Полный реальный автономный production OPEN → CLOSE остаётся отдельной проверкой.

## Результат проверки 19 октября 2026

Период: **21.07.2026 00:00 → 19.10.2026 00:00 UTC**, правая граница исключена.
Источник — официальные Binance Spot BTCUSDT 15m ZIP и их CHECKSUM, независимо
загруженные по HTTPS. 12 800 свечей вместе с точным прогревом, 8640 решений.
SHA256 CSV: `ae784feba0e5bf739afa22d997820fb937f9790d613cbd3640dccc0a4def2c58`.
Из тех же свечей получены закрытые 1h/4h, без смешения бирж и синтетических цен.

| Результат 90 дней | main | Эта ветка |
|---|---:|---:|
| Допустимые LONG / SHORT | 4 / 0 | 4 / 0 |
| Открыто / закрыто | 3 / 3 | 3 / 3 |
| TP / SL | 1 / 2 | 1 / 2 |
| Отказ: позиция уже открыта | 1 | 1 |
| Net PnL после издержек | +3.63045829 USDT | +3.63045829 USDT |
| Комиссии / slippage | 12.01564611 / 6.00782846 USDT | То же |
| Max drawdown | 0.49508551% | 0.49508551% |
| Технические ошибки исполнения | 0 | 0 |

Все 8640 торговых решений совпали семантически (диагностический code identity
отражает изменённый файл стратегии); equity и сделки совпали полностью. Новая
проверка origin не удаляет ни одного допустимого сигнала этого периода, но
регрессионный случай с заимствованным чужим BOS теперь отклоняется.

Первый сработавший отказ на 8636 WAIT-свечах:

| Причина | Количество |
|---|---:|
| MTF_NOT_ALIGNED | 5009 |
| NO_CONFIRMED_SETUP | 3493 |
| TREND_NOT_ALIGNED | 56 |
| TREND_TOO_WEAK | 47 |
| OPPOSING_LEVEL_TOO_CLOSE | 28 |
| VOLATILITY_FILTER | 2 |
| OPPOSING_LIQUIDITY | 1 |

Это последовательные первые отказы, не независимая частота каждого фильтра.
При согласованном DOWN: 1415 свечей без retest, 24 retest против тренда,
18 отказов по силе, 9 по ближайшему support, 2 по volatility. Поэтому SHORT
не прошёл все условия этой выборки; код SHORT достижим и проверен изолированно.
За последние **30 дней: 0 сигналов** (1666 MTF, 1162 без retest, остальные
52 — другие фильтры). Нельзя обещать первую сделку сразу после deploy.

Настоящий сигнал **21.07.2026 12:45 UTC** отдельно пересчитан по причинному
rolling-префиксу и исполнен Service/engine на настоящем локальном PostgreSQL.
LONG: entry 66549.428085, размер 0.030052850303 BTC,
SL 66220.421214725092385, TP 67107.667570549815230.
Автоматический STOP_LOSS 21.07.2026 18:00 UTC, итог −14.87176777 USDT,
баланс 9985.12823223; комиссии 3.98911735, slippage 1.99455645 USDT.
Позиция восстановлена новым контроллером перед закрытием; результат сохранён.
Это реальный **исторический** сигнал на изолированном engine/SQL, не Render LIVE.

PostgreSQL: 6 сценариев LONG/SHORT × TP/SL/оба уровня и 8 групп проверок
ролей, атомарности, дубликатов, restart, stale/recovery, SQL failure и DB outage.
Python: **1280 PASS в полном прогоне** с обоими PostgreSQL opt-in; ещё 2 новые
проверки owner read-only/отсутствующего RPC прошли в отдельном прогоне файла
из 33 тестов. Итого **1282 уникальных Python-теста проверены**.
17 JavaScript-наборов PASS; изменённый Auto42 adapter повторно проверен: 24 PASS.
Синтаксис Python/JS и импорт app.main PASS. Одно существующее предупреждение
Starlette/AnyIO не связано с изменениями. Chromium/HTTP owner UI PASS на 430 px,
с отдельной SQLite и явно тестовой display-котировкой; ни одной сделки.

Read-only production evidence: `/api/health` HTTP200, owner status без доступа
HTTP401. [GitHub run 39214634109](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39214634109)
19.10.2026 07:13 UTC сохранил контракт: ON, `NO_NEW_WORK`,
`MTF_NOT_ALIGNED`, processed=false, opened=0, closed=0. Это дедуплицированный
no-op, **не доказательство новой обработанной свечи или LIVE OPEN/CLOSE**.
Между запусками GitHub наблюдаются многочасовые интервалы; другие ticks от
Cloudflare и uptime Render в этой сессии не подтверждены.

`NO_VERIFIED_PRODUCTION_CYCLE` — отсутствие live-доказательств в мониторе,
не торговый фильтр и не запрет первой сделки. Practice/TEST_ONLY используют
иной путь получения команды/контекста и потому не доказывают автоматический
strategy signal. На проверенной истории нет логического запрета всех входов.
Конкретный последний retest на Render требует владельческого snapshot/SHA:
доступ к приватным журналам и рабочей Supabase здесь не использовался.

Выполнены отдельные code review и security review по `docs/ecc/TRADING_REVIEW.md`:
причинность, исходный breakout, Decimal/risk/costs, bounded catch-up, CAS/idempotency,
owner/CSRF, allowlist публичных GET, SQL права, отсутствие exchange writers и
секретов. Нерешённых critical/high code findings не обнаружено. Ограничения
hosting/forward-доказательств перечислены явно и не объявлены пройденными.

**TECHNICAL_EXECUTION = PASS**

**LIVE_AUTONOMOUS_EXECUTION = WAITING_FOR_REAL_SIGNAL**

**PRODUCTION_VERIFIED = FALSE**

Для production-доказательства остаются ручной review/merge/deploy владельцем,
проверка durable состояния и фактических интервалов scheduler, затем настоящий
естественный сигнал и связанный Render/Supabase OPEN → CLOSE без искусственных
команд. Платные сервисы/API не подключены и не созданы.

## Изменённые файлы

- Runtime: `app/automated/{api,engine,service,storage,strategy}.py`.
- Интерфейс: `static/auto42.js`, `static/index.html`.
- Изолированная проверка и данные: `scripts/download_auto42_history.py`,
  `scripts/verify_auto42_postgres.py`, `scripts/verify_auto42_execution.py`
  (только актуализация тестового origin), `scripts/auto42_trade_history.sql`.
- Регрессии: `tests/test_auto42.py`, `tests/test_auto42_completion.py`,
  `tests/test_auto42_frontend.cjs`, `tests/test_auto42_mode_isolation.py`,
  `tests/test_auto42_postgres.py`, `tests/test_auto42_retest_monitor_fixes.py`,
  `tests/test_first_paper_trade_audit.py`. Старые фикстуры теперь явно передают
  origin соответствующего breakout; ожидания риска/доходности не ослаблены.
- Отчёт: этот файл, `docs/AURA_AUTO42_COMPLETION_EVIDENCE.json`,
  `docs/AURA_LIVE_PAPER_TECHNICAL_VERIFICATION.json` (повторный изолированный
  прогон, привязанный к текущему коду; не LIVE).

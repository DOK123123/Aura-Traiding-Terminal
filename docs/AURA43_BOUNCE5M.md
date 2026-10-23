# Aura 4.3: experimental Support/Resistance Bounce 5m

## Архитектура и совместимость

Источник — только BTCUSDT Bitget USDT-M perpetual Futures, существующий публичный
GET allowlist. Новый сценарий SR_BOUNCE/5m использует тот же Service, Paper Engine,
Store, risk guards, journal, комиссии, проскальзывание и сохранение Supabase.
Отдельного execution engine и production test-signal endpoint нет.

Аудит выявил два ограничения исходной архитектуры: config/hash защищены от
изменения обычным commit RPC, а frozen protocol hash связан с persisted account.
Решение: отдельный frozen protocol для Bounce, дополнительный узкий RPC выбора
и неизменяемый STRATEGY_CHANGE receipt. Registry/protocol/default selection
Donchian не расширяются и не пересчитываются. Его прежний hash сохранён:
`f2bf45afdd0e7fc324afd1c4977376aacd804d02fc6f9494212fc05e45b61e69`.
Donchian сигналы, SL/TP, параметры и поведение остаются прежними.

## Правила сигнала

Все входные свечи закрытые, 5m, UTC. Уровни рассчитываются на **48 свечах до
касания**, исключая и touch bar, и confirmation bar. Поддержка — min(low),
сопротивление — max(high). ATR14 использует только соответствующий закрытый prefix.

LONG:
- low предыдущей touch-свечи находится между support−0.5 ATR и support+0.15 ATR;
- touch.close >= support;
- текущая закрытая confirmation-свеча bullish и close > touch.high.

SHORT — зеркально: high touch между resistance−0.15 ATR и resistance+0.5 ATR,
touch.close <= resistance; bearish confirmation close < touch.low.
Два одновременно подтверждённых направления не дают входа.

SL distance — max(1.5 ATR подтверждающей свечи, расстояние за оба wick с буфером
0.25 ATR). Stop привязан к подтверждённой структуре и округляется наружу к tick.
TP для **новой** стратегии рассчитывается от виртуальной цены исполнения после
entry slippage: 1.5 × расстояние entry→SL. Trigger округляется консервативно
к Bitget tick 0.10; отклонение от точных 1.5R меньше одного tick. Это gross price R,
не net reward/risk после комиссий. Donchian TP calculation не меняется.

Production engine сохраняет сигнал и ждёт next-open по своей существующей модели
CLOSED_SIGNAL_NEXT_OPEN. Обработка и виртуальная проверка SL/TP происходят на
следующей доступной закрытой свече, а не реальным биржевым stop order. При
одновременном SL/TP применяется прежний консервативный SL-first.

Риск максимум 0.5% с учётом stop execution costs, дневной лимит 2%, просадка 10%,
не более одной позиции и номинал <=2000 USDT. Commission 0.10% и slippage 0.05%
на сторону остаются общими; qty step/min qty/min notional и price tick проверяются
тем же кодом. Funding по-прежнему не моделируется. Stale/invalid/source errors
запрещают вход. Watermark, unique candle/event keys и CAS защищают от дублей.

## Переключение и постоянное хранение

Owner Panel → **AURA 4.3 ACTIVE PAPER v3 · BITGET FUTURES**, перед START/STOP:
выбор «Donchian 15m» / «Support/Resistance Bounce 5m · EXPERIMENTAL» и кнопка
**Сохранить стратегию · PAPER останется OFF**. Текущая активная конфигурация
по-прежнему показывается отдельным полем. Ни выбор, ни публикация не включают PAPER.

POST `/api/active43/strategy` защищён существующими owner auth + CSRF.
Принимает только choice, UUID request_id, expected_revision и точное confirmation.
Scheduler token не даёт права выбора, произвольные параметры/баланс запрещены.
API начинает с peek(), не вызывает load/seed; отсутствующий счёт отклоняется.
API, UI и SQL требуют OFF, ноль position/pending/pending_exit, recovery=false,
отсутствие emergency и пройденные сохранённые risk guards.

Новая миграция: `scripts/active43_bitget_strategy_selection.sql`.
Она только добавляет SECURITY DEFINER функцию `aura_active43_bitget_select_strategy`
с EXECUTE для service_role. Не создаёт портфель/таблицы, не вызывает load/reset,
не меняет существующие RPC и торговые строки при применении. Повторное применение
проверено. PUBLIC/anon/authenticated запрещены. Production SQL не применялся.

Функция блокирует singleton account row, проверяет revision, два точных config/hash,
границы OFF и единственное событие STRATEGY_CHANGE. Разрешены только конфигурация,
идентификатор receipt и заранее перечисленные analysis/evidence поля; сравнение
остального состояния гарантирует неизменность финансов/epoch/policy/позиции/риска.
Атомарно записывает receipt и новую config в тот же существующий счёт. Обычный
commit RPC **по-прежнему** не позволяет менять config. При ошибке — rollback.

Баланс, equity, комиссии, realized PnL, статистика, daily/drawdown counters и вся
история сохраняются. Сбрасываются только analysis watermark/cache/quote и текущая
цепочка production-cycle evidence: цикл прежней стратегии не подтверждает новую.
Предыдущие события не удаляются. История/статистика общие для портфеля; новые Bounce
positions/trades помечены strategy=SR_BOUNCE, timeframe=5m и причиной входа.

Процесс восстанавливает выбор из Supabase только при валидном immutable receipt,
config hash и scope; неподтверждённая подмена даёт CONFIG_CHANGED. Это работает
между рестартами и разными инстансами. Гонка tick со сменой config завершает старый
tick безопасным CONFIG_CHANGED; следующий читает актуальную config. Смена не
позволяет обнулить дневной лимит или получить другую начальную сумму.

Существующий Cloudflare saved_mode продолжает вызывать тот же /tick; его код,
частота, операция и секреты не меняются. После рестарта status/первый tick
синхронизирует выбранный config; строго peek-only readiness до синхронизации может
консервативно показать CONFIG_CHANGED/BLOCKED. Не обходить его через initialize.

## Изолированная быстрая проверка

Локально из корня репозитория:

```sh
python -m scripts.verify_active43_bounce --output /tmp/bounce-paper-test.json
```

Нужен новый выходной файл; существующий не перезаписывается. Генерируются только
воспроизводимые **синтетические** closed 5m bars. Направление вычисляет настоящая
новая стратегия, исполнение — production Service/engine. Временный checkpoint
проверяет восстановление позиции. Нет HTTP clients, Supabase URL/ключей, публичной
кнопки или влияния на production Auto Paper. RENDER guard запрещает запуск на Render.

Шесть случаев: LONG/SHORT × TP/SL/BOTH. Каждый имеет ровно один OPEN/CLOSE,
комиссии, slippage, риск, конечный баланс, независимую перепроверку PnL и duplicate
защиту. Полные позиции/выходы — в JSON отчёте. Эти сделки никогда не LIVE VERIFIED.

Отдельный реальный локальный PostgreSQL verifier выполняет те же шесть случаев
через Store/SQL, выбор Donchian→Bounce, restart с default config и восстановление
из receipt, CAS, RLS, запрет финансовой подмены, неизменность ordinary commit.
Принудительная ошибка **после INSERT события до UPDATE счёта** откатывает обе записи.
Проверяется также запрет SQL выбора на OFF-счёте с открытой позицией.

## Реальные данные: ограниченная проверка частоты

Read-only публичный scan завершился 2026-10-23 09:45 UTC. Одинаковые 60 часов
Bitget Futures OHLC, causal warmup; сравнивались последние **10 общих часов**:

| Стратегия | LONG кандидаты | SHORT кандидаты | Всего |
| --- | ---: | ---: | ---: |
| SR Bounce 5m | 2 | 2 | 4 |
| Donchian 15m | 1 | 0 | 1 |

Это **не количество сделок**: engine может отклонить кандидата из-за позиции,
стоимости/риска и прочих guards. Последовательный OPEN→CLOSE/PnL backtest на этой реальной истории
не выполнялся. Десяти часов недостаточно для вывода о стабильной частоте,
качестве сигналов или прибыльности. Параметры не подбирались по этому периоду.
Данные Spot/Bybit и старые Research Lab PR не включались.

Дополнительная изолированная проверка next-open entry costs для этих четырёх
кандидатов: три прошли существующие sizing/cost guards (risk 10.25–11.76 USDT,
notional <2000 USDT); у последнего ещё не было следующей закрытой свечи. Каждому
кандидату выделялось отдельное тестовое состояние 10000 USDT, без записи в Store.
Это не число возможных последовательных сделок: перекрытие позиций, дневные
ограничения и последующий SL/TP/PnL в этой проверке не моделировались.

Воспроизведение того же окна/проверка data hashes:

```sh
python -m scripts.scan_active43_bounce --end 1792748700 --output /tmp/bounce-bitget-scan.json
```

Это локальный read-only инструмент, без execution или тестовых сигналов в
production. Только реальный публичный Bitget; stale/API error дают BLOCKED,
синтетической подмены нет. Если провайдер исправит исторические свечи, hashes
могут отличаться. Summary и hashes включены в AURA43_BOUNCE5M_VERIFICATION.json.

## Публикация владельцем, не часть этой задачи

1. После review/Merge вручную применить **только** новую миграцию
   `scripts/active43_bitget_strategy_selection.sql` в существующем Supabase SQL Editor.
   Base Bitget schema должна уже существовать. Не запускать reset/старые init SQL.
2. Render Deploy одобренного main. Новые env, ключи, сервисы и Cloudflare Deploy
   не нужны. PAPER остаётся в сохранённом OFF; Donchian — default, выбор не автоматический.
3. В Owner Panel при OFF/empty/guards выбрать Bounce 5m и сохранить; проверить
   active config и OFF после refresh/restart. Для естественного PAPER OPEN→CLOSE
   потребуется отдельное решение владельца включить существующий START PAPER.
   Эта задача не включает торговлю и не подтверждает цикл на Render.

Rollback: пока OFF и счёт пуст, сохранить Donchian 15m **до** отката к старому коду,
не знающему Bounce. С открытой позицией выбор запрещён: не сбрасывать счёт ради
отката, сохранять существующие защитные выходы. Дополнительный RPC можно оставить
неиспользуемым; старые tables/RPC не менялись. Free Render/Cloudflare остаются
best-effort, не гарантией 24/7. Paper SL/TP не существуют как ордера Bitget.

## Review

Code review: прежние protocol hashes/default Donchian и расчёты сохранены;
исключение только для Bounce TP 1.5R. Prefix causality, closed data, CAS/restart,
fees/size/risk и SQL compatibility проверены тестами. Security review: owner+CSRF,
строгий input allowlist, SELECT FOR UPDATE, неизменность финансов и RLS,
нет публичного симулятора, реальных ордеров, секретов в UI/отчётах или SQL.
Критических/high замечаний не обнаружено. Ограничения — малая реальная выборка,
нет profitability proof/production natural cycle, обязательная additive migration.
Aura 4.2/Practice и существующий Scheduler не менялись. Merge/Deploy и production
SQL/торговые команды в этой работе не выполнялись.


## Финальная проверка

- Полный Python suite с реальным локальным PostgreSQL: **1607 passed, 2 skipped**,
  255.13 s. Skip — существующие standalone Auto42/Practice PostgreSQL opt-in.
- Полный Node suite: **239 passed**. Три новые регрессии selector/OFF/auth-response.
- Bounce subset: **26 passed**; signal causality, LONG/SHORT SL/TP/BOTH, risk,
  duplicate/restart, owner auth/CSRF/strict input, missing account без seed,
  race tick↔selection, network-free simulation и CLI guards.
- PostgreSQL: **15 групп проверок**, шесть новых Bounce циклов плюс семь прежних
  execution scenarios, RLS/legacy isolation, forced-after-insert rollback, CAS и
  запрет финансовой подмены. Миграция применена дважды только в локальном контейнере.
- Реальный локальный Chromium, viewport 390px: owner выбрал Bounce через серверный
  API; ровно один POST /strategy при двойном нажатии, mode OFF, баланс 10000
  неизменён. Selector 294px внутри panel 366px. Это memory fixture, не production.
- AST всех Python-файлов, import app.main, node --check и diff --check: PASS.
  Одно существующее предупреждение Starlette/anyio deprecation.

PRODUCTION_PAPER_VERIFIED = FALSE. TECHNICAL_SIMULATION = PASS.

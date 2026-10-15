# Aura Auto Paper 4.2 — сквозная проверка

База main: `5dfcf37f58789b1ef4373309ae3e69169fff1767`.
Это проверка действующей **Auto42**, не Historical Pattern, не новый алгоритм
и не миграция на Bitget. Параметры, источник Binance Spot, Supabase, обычный Paper,
Replay Intelligence, диагностики бирж, scheduler и владелец не изменяются.

## Три независимых вида доказательств

1. **ISOLATED TECHNICAL TEST**: production Service/strategy/engine/SQLiteStore,
   только временные тестовые каталоги и синтетический контекст TEST ONLY.
   Доказывает wiring/бухгалтерию; не доказывает историческую стратегию или Supabase.
2. **HISTORICAL REPLAY**: реальный локальный CSV, production market structure,
   strategy и Decimal advance. Отдельный старт 10000 для каждого периода.
   Доказывает последовательный расчёт на данных; не доказывает live uptime/прибыльность.
3. **LIVE AUTONOMOUS**: требуется наблюдённая production-цепочка signal → OPEN →
   persisted position → restart/ticks → CLOSE → PnL. Статус **NOT_TESTED**,
   пока такой цикл не наблюдён. Ни HTTP200 health, ни успешный tick не заменяют его.

## Точные production-пути

| Этап | Код |
|---|---|
| Public Binance Spot GET / закрытые 15m свечи | `app/intelligence/market_context.py:fetch_window`, `retry_page`; `app/lab/data.py:public_page` |
| Rolling window / closed MTF / pivots / BOS / CHoCH / retest | `market_context.py:analyze_window`; `research/market_intelligence/structure.py:segment_states`; `app/lab/series.py:higher` |
| Формирование текущего snapshot / свежесть / кэш | `MarketContext.refresh`, `MarketContext.snapshot`; `app/automated/market_data.py:snapshot_for_auto` |
| Подтверждение сигнала / source hash / 15m/1h/4h / фильтры | `app/automated/strategy.py:strategy`, `PARAMETERS` |
| Владелец / CSRF / scheduler token | `app/automated/api.py:control`, `scheduler`, `tick`; `app/paper/api.py:owner`, `mutation` |
| START baseline / tick / retry / CAS conflict | `app/automated/service.py:Service.control`, `snapshot`, `_tick`, `_bounded_tick` |
| Риск / sizing | `app/automated/engine.py:risk_reason`, `open_virtual` |
| Pending → next-open fill / candle watermark | `engine.py:advance` |
| Stop/target, adverse gaps, same-bar SL-first | `engine.py:protective` |
| Fee/slippage primitives | `app/lab/execution.py:fee`, `fill` |
| Gross/net PnL и баланс | `engine.py:close_virtual`, `validate` |
| Mark-to-market liquidation equity / DD | `engine.py:liquidation_equity`, `mark`, `roll_day` |
| Хранение / журнал / восстановление | `app/automated/storage.py:SupabaseStore.load`, `commit`, `history`, `verify_envelope`; SQLiteStore используется только изолированно |
| Транзакция PostgreSQL | `scripts/auto42_schema.sql:aura_auto42_commit`, row lock/revision + unique operation/event ID |
| Дашборд / журнал | `Service.dashboard`; `/api/auto42/status`, `/api/auto42/journal`; `static/auto42.js` |
| Внешний trigger | `deploy/auto42-worker/worker.mjs:scheduled → run`; `.github/workflows/aura-auto42.yml`; `scripts/auto42_scheduler.py` |

Пропущенных соединений в этой цепочке в рамках доступной проверки не обнаружено.
Production-код стратегии, исполнения и хранения не исправлялся без доказанного дефекта.

## Финансовая математика

Текущая `engine.POLICY`, не предположение о тарифе биржи:
10000 USDT, риск 0.5%, max notional 2000, max positions 1,
лимит дневных потерь 2%, drawdown 10%, комиссия **0.10% за сторону**,
adverse slippage **0.05% на fill**. Новых настроек или overrides не добавлено.

LONG entry = raw_open × 1.0005; exit = raw_exit × 0.9995. SHORT наоборот.
Fee = ceil_1e-8(fill × quantity × .001). Quantity вниз до 1e-12,
fee-inclusive worst-case stop risk ≤0.5% liquidation equity, notional ≤2000,
collateral + entry fee ≤ balance. На gap через stop фактический убыток может
превысить исходный stop budget — stop не является гарантией цены.

Gross PnL = sign × (exit_fill − entry_fill) × quantity; net = gross − обе комиссии.
Entry fee списывается при входе; при закрытии balance += gross − exit fee.
Invariant: balance = 10000 + realized_net − entry_fee_открытой_позиции.
Slippage уже включено в fill/PnL и показывается отдельно; второй раз не вычитается.
Equity учитывает hypothetical adverse exit fill и exit fee, поэтому отличается
от realized balance при открытой позиции. Процент доходности replay — по equity;
realized PnL отражает только закрытые сделки.

Сигнал только на закрытии. Pending исполняется на open следующей свечи **при её
закрытии**, как в production closed-candle settlement. Timestamp entry и время
фактической записи события различаются. Не используются high/low signal-candle.
Если SL и TP затронуты одновременно — SL_FIRST. Gap через TP — по target без бонуса.
Это виртуальная 1x линейная модель на Spot ценах; funding/borrow/liquidation не моделируются.

## Изолированный harness

`scripts/verify_auto42_execution.py` использует настоящие production классы,
но никогда не вызывает `configured()`, SupabaseStore, live API или owner controls.
Все SQLite файлы находятся в `TemporaryDirectory`, epoch начинается с TEST_ONLY.
Контекст специально синтетический; результат **не является сигналом реального рынка**.

Пять сценариев: LONG TP, LONG SL, SHORT TP, SHORT SL, LONG simultaneous SL/TP.
Каждый: настоящий START в тестовом контроллере → новая закрытая свеча → pending →
два конкурентных контроллера → ровно один OPEN → новый объект store/controller →
восстановление позиции → повторный tick → ровно один CLOSE.
Независимый Decimal oracle проверяет entry/exit, обе комиссии, slippage, net PnL,
balance и risk/notional. Отдельно проверены stale/missing данные, recovery, STOP,
EMERGENCY и запрет START при emergency. Нет owner reset или live account writes.

**Ограничение:** SQLite restart — реконструкция store/controller с того же файла,
не доказательство restart удалённого PostgreSQL или реально перезапущенного Render.
Реальные Supabase SQL/RPC в этом harness не выполнялись. Их транспортные/error
контракты проверяются существующими offline mock tests, не выдаются за live DB test.

## Исторический replay и причинность

`scripts/replay_auto42_verification.py` использует существующий
`load_binance_csv` и вызывает production `analyze_window`, `strategy`, `advance`.
Никакой подмены стратегии фикстурами. Единственный источник цен — приложенный CSV;
запросы в Binance, Bitget или private APIs не выполняются.

Источник: `BTCUSDT-15m-2026-05_to_09.csv`, **14688** свечей, 2026-05-01 — 2026-10-01 UTC.
SHA256: `cbe142f776e2ddebe66b5e33a601ac679cf1988ad9b16b52799bc336fac1cb07`.
Импортёр проверил 12 columns, timestamps ms/us, OHLCV, порядок, дубликаты и gaps.
**Происхождение Binance заявлено пользователем; CHECKSUM официального архива для
этого CSV независимо не сверялся.** Валидность OHLCV не доказывает происхождение цен.
Production SOURCE сохранён для проверки signal contract; это не заявление о live API fetch.

Каждый snapshot имеет точный production rolling start:
`floor(closed_at / 4h) × 4h − 4160 × 15m`. Прогрев не менее 4160 base candles;
1h/4h только полные UTC-блоки и собственный прогрев 250. Нет forward-fill.
Невалидный CSV останавливает импорт, а не ремонтируется. Никаких настроек не подбирали.

Для bounded offline расчёта переиспользованы **те же чистые production states**
для префиксов одного 4h window. PrefixCache готовит states ограниченного блока,
но возвращает только строки до закрытого cutoff; strategy всегда получает только
raw prefix. Native `analyze_window` сохраняет сборку/обрезку events, MTF и source hash.
Сравнены все поля всех трёх snapshots с native пересчётом на **8 реальных cutoffs**
и 4 synthetic prefixes; изменение будущих свечей не меняет текущие states.
Это memoization причинных функций, не использование будущих исходов.
Patch существует только внутри offline worker; в web app не устанавливается.

Два CPU workers максимум, <=4175 candles на analysis, <=2 outstanding jobs,
checkpoint после каждого ограниченного блока с fsync, data/code/config fingerprint,
валидируемая последовательность и восстановление после незавершённой последней записи.
Никакого replay расчёта в Render request. Файл исходной истории/checkpoint/full curve
не коммитятся; small summary содержит journal закрытых сделок и SHA полного JSON.

Отказы стратегии — **первый проваленный фильтр в production порядке**, не независимое
число всех одновременно нарушенных условий. Execution rejections отделены от WAIT.
Кэш decisions общий для периодов, но balance, positions, PnL и risk state каждого
7/30/90-прогона начинаются отдельно. Новый сигнал на последнем cutoff остаётся
pending при отсутствии следующей свечи; закрытие/вход задним числом не создаются.

## Автономность и доступная production-проверка

Код не зависит от открытого браузера: Cloudflare/GitHub вызывают защищённый tick;
Render может проснуться по запросу. Cloudflare и GitHub configuration cron:
`2-59/5 * * * *` UTC. Это не гарантия точного пятиминутного SLA: возможны задержки,
cold start и upstream ошибки. GitHub backup и Worker могут сработать вместе:
per-process singleflight + Supabase row lock/CAS/unique tick ID защищают от дублей.

OFF без позиции сохраняет heartbeat и не продвигает candle watermark. STOP/EMERGENCY
отменяют pending/новые входы, но не отключают защитные выходы существующей позиции.
При missed candle pending отменяется: нет ретроспективного входа. При неизвестном gap
цена выхода не выдумывается. Data errors блокируют входы; retryable error → PAUSED
с recovery_armed; свежие данные восстанавливают ON только ранее включённого владельцем
режима. STOP disarms recovery. Risk/emergency pause не превращается самовольно в ON.
История и watermark сохраняются транзакционно в Supabase; browser/Render local disk не нужны.

Проверено read-only из этой сессии:

- Render `/api/health`: HTTP200 `status=ok`.
- `/api/auto42/status` без owner auth: HTTP401.
- GitHub scheduled run **#19**, id `38801816188`, job `116652484892`: SUCCESS.
  Создан `2026-10-15 20:25:25 UTC`; source commit `851ab673…`.
  Безопасно извлечённая строка лога: `outcome=NO_NEW_CANDLE mode=ON
  decision=MTF_NOT_ALIGNED processed=False opened=0 closed=0`.
  Существующий scheduler client перед SUCCESS проверяет `state_saved=true`,
  `paper_only=true`, `exchange_execution=false` и outcome contract.

Это свидетельство реального scheduler → backend → accepted save contract, а не
прямая проверка таблиц Supabase и не наблюдённый OPEN/CLOSE. Cloudflare deployment,
его runtime logs, owner journal и фактический backend SHA недоступны через имеющиеся
подключения. Health не содержит SHA. В production START/STOP/RESET, ticks или
Supabase запросов из этой задачи не выполнялось. Render/Android deploy не проверен.

## Запуск и панель владельца

Из корня репозитория с requirements.txt:

```bash
python -m scripts.verify_auto42_execution
python -m scripts.replay_auto42_verification --csv /path/BTCUSDT-15m-2026-05_to_09.csv --output /tmp/auto42-replay.json --workers 2 --max-seconds 1500
python -m scripts.build_auto42_verification_report --replay /tmp/auto42-replay.json --output docs/AURA_AUTO42_EXECUTION_VERIFICATION.json
```

При budget limit повторить ту же команду replay: checkpoint и fingerprint не позволяют
повторно исполнить уже вычисленные свечи/незаметно смешать production версии. Скрипты
не читают trading keys/владельческий portfolio config. В данной managed sandbox
тестовый launcher использует существующий `enable_sandbox_poll`; это не runtime patch.

После обычного deploy проверенного commit на Render открыть с Android
https://aura-traiding-terminal.onrender.com → **PAPER EXECUTION VERIFICATION** →
войти владельцем `aura` → раскрыть три отдельные карточки. Новый endpoint:
GET `/api/auto42-verification`, owner-only, без DB/market запросов или test-trade кнопок.
Включать флаги, менять credentials, SQL или стратегию не требуется.
Панель показывает сохранённое offline доказательство и проверяет checksum + SHA
11 production файлов; если код меняется — прежний PASS становится NOT_TESTED.
Live статус принудительно NOT_TESTED: offline artifact не может выставить live PASS.

Для независимой production-проверки **без принудительной сделки** наблюдать существующий
owner journal через несколько новых закрытий свечи с закрытым браузером, затем
сверить scheduler run, DECISION, OPEN с source/signal timestamp, сохранённую позицию,
CLOSE reason, обе комиссии и balance=10000+net. Если стратегия WAIT — OPEN не должен
появляться, это не сбой исполнения. Не нажимать START/RESET ради проверки;
последний доступный лог уже ON, текущий режим проверяется только владельцем.

На Android вручную проверить 320–430px, раскрытие деталей, формат TEST ONLY,
отсутствие горизонтального скролла, обработку 401/timeout и восстановление кнопки.
Настоящий browser/mobile тест в этой среде **NOT RUN**.

## Фактически выполненные расчёты

Все периоды UTC, конец исключён по open time свечи: 2026-10-01 00:00.

| Период | Свечи | LONG / SHORT / WAIT | Открыто / закрыто | TP / SL | Net PnL USDT | Equity | DD % | Win rate | PF |
|---|---:|---|---|---|---:|---:|---:|---:|---:|
| 7 дней | 672 | 0 / 0 / 672 | 0 / 0 | 0 / 0 | 0 | 10000 | 0 | — | — |
| 30 дней | 2880 | 0 / 0 / 2880 | 0 / 0 | 0 / 0 | 0 | 10000 | 0 | — | — |
| 90 дней | 8640 | 7 / 0 / 8633 | 5 / 5 | 1 / 4 | -39.27623273 | 9960.72376727 | 0.85595939 | 20.00000000 | 0.47283609 |

7 дней: 2026-09-24 — 2026-10-01. 30 дней: 2026-09-01 — 2026-10-01.
90 дней: 2026-07-03 — 2026-10-01. Все три счета стартовали независимо с 10000 USDT.
Открытых позиций и pending на конце нет. Execution errors — **0** во всех периодах.
Комиссии за 90 дней **19.98070449 USDT**, slippage **9.99034991 USDT** (уже в fill/PnL).
До комиссий, после моделируемого slippage: gross price PnL **−19.29552824 USDT**.
В 7/30 дней издержки 0; win rate/PF **undefined**, не 0% и не бесконечная прибыль.
PASS historical означает завершённый корректный replay; **не положительный edge**. Всего 5 сделок статистически недостаточно.

### Первые проваленные фильтры (WAIT)

| Причина | 7 дней | 30 дней | 90 дней |
|---|---:|---:|---:|
| MTF_NOT_ALIGNED | 565 | 1767 | 5009 |
| NO_CONFIRMED_SETUP | 100 | 1065 | 3496 |
| OPPOSING_LEVEL_TOO_CLOSE | 4 | 14 | 27 |
| OPPOSING_LIQUIDITY | 0 | 0 | 1 |
| TREND_NOT_ALIGNED | 3 | 18 | 62 |
| TREND_TOO_WEAK | 0 | 15 | 37 |
| VOLATILITY_FILTER | 0 | 1 | 1 |

Это отсутствие подтверждённого setup, а не ошибка вычисления. MTF alignment и отсутствие retest — главные фактические причины WAIT.
Уже подтверждённых сигналов, отклонённых execution: **2 POSITION_ALREADY_OPEN** за 90 дней, 0 за 7/30. Не смешиваются с WAIT.
### Журнал реальных исторических paper-сделок (90 дней)

Это результат replay, **не сделки владельца на Render**. Цены fill с adverse slippage.
| UTC вход | Направление | Entry fill | UTC выход | Exit fill | Причина | Net USDT |
|---|---|---:|---|---:|---|---:|
| 2026-07-10 09:45 | LONG | 64498.343055000000 | 2026-07-10 12:15 | 64094.464782008985149425 | STOP_LOSS | -16.51115535 |
| 2026-07-20 18:15 | LONG | 65785.916520000000 | 2026-07-20 19:00 | 65175.540839676491671025 | STOP_LOSS | -22.53786759 |
| 2026-07-21 08:00 | LONG | 66219.953430000000 | 2026-07-22 07:45 | 65731.7739726711645073525 | STOP_LOSS | -18.72943585 |
| 2026-08-05 19:15 | LONG | 64917.952755000000 | 2026-08-06 01:30 | 64504.4557811862698056225 | STOP_LOSS | -16.72632483 |
| 2026-08-20 23:30 | LONG | 73248.606000000000 | 2026-08-21 01:30 | 74686.7624904151929106600 | TAKE_PROFIT | 35.22855089 |

### Помесячный итог 90-дневного счёта

| Месяц | Закрыто | Realized net USDT | Ending equity |
|---|---:|---:|---:|
| 2026-07 | 3 | -57.77845879 | 9942.22154121 |
| 2026-08 | 2 | 18.50222606 | 9960.72376727 |
| 2026-09 | 0 | 0 | 9960.72376727 |

### Независимая проверка accounting

Отдельный oracle в `scripts/build_auto42_verification_report.py:audit_accounting` без production fee/fill проверил все **5** реальных закрытых сделок:
entry/exit fills, обе комиссии, Net PnL, final balance, notional/risk bounds, next-open timestamp, total slippage и profit factor совпали.
Расчёт DD независимо по полной close equity curve дал **0.85595939%**, что совпало с engine DD (который дополнительно проверяет open marks).
Полный raw JSON (включая equity curve) сохранён локально в `/workspace/research-output/auto42-verification/replay.json`.
Его SHA256: `1b6ff0b792fbe6ad18d937f484f61a8a8c75dae3044e5ae33beee2dbb3a5d946`.
Коммитится компактный `docs/AURA_AUTO42_EXECUTION_VERIFICATION.json`: все закрытые сделки, итог каждого периода, metadata, независимый accounting и TEST ONLY доказательства.
Исходный CSV, большой replay JSON и checkpoint не публикуются в Git. Полный результат восстанавливается командами выше.

### Найденные и исправленные проблемы

- **Production critical/high:** подтверждённых дефектов в исполнении не найдено. Рабочий код не переписан.
- **Diagnostic delivery / medium:** первый запуск нового runner завершил вычисления, но запись отчёта остановилась из-за отсутствующей ссылки SOURCE. Исправлено на `mc.SOURCE`, добавлен regression на завершённый checkpoint → JSON. Сигналы восстановлены из checkpoint, без повторного вычисления или подделки.
- **Diagnostic reliability / medium:** ограничены outstanding CPU jobs, добавлены fsync/checkpoint identity/sequence checks и восстановление неполной последней записи. Complete corrupt lines не пропускаются.
- **Evidence safety:** отсутствие/повреждение report или изменение production hashes снимает PASS; live PASS недоступен из offline artifact.
- **Остаётся ограничением:** Supabase restart/actual open-close, Cloudflare uptime и Android browser test не подтверждены этой сессией.

### Вывод

Production-функции способны генерировать допустимый сигнал, открыть, сохранить и закрыть виртуальную позицию с проверенной математикой.
В сентябре эта стратегия не нашла разрешённых входов на данном CSV. Это не доказывает неисправность движка.
Преимущество не подтверждено: 90 дней убыточны и содержат лишь 5 сделок. Следующий безопасный шаг — наблюдение существующего owner-controlled forward paper journal без ослабления фильтров и принудительных сделок.

## Итог проверок, review и поставка

- Полный Python suite: **1174 passed**, 1 deprecation warning Starlette/AnyIO,
  72.54s. Ничего не пропущено самим pytest; количество тестов — не coverage.
- Все 14 JS suites: **177 passed**; после уточнения UI-надписи ещё раз 3 новых JS tests PASS.
- Python AST всех app/scripts/tests, `import app.main`, новый JS `node --check`: PASS.
- Импорт текущего owner evidence endpoint: isolated PASS / historical PASS /
  live NOT_TESTED, `code_matches=true`.
- Replay: **8640** уникальных решений из checkpoint; 7/30/90 все завершены,
  execution errors 0; независимый financial oracle PASS по 5 закрытым сделкам.
- Native/batched real-data equality: **8** cutoffs × все 3 frames, все поля совпали.
  Future-mutation/prefix/gap/closed-candle/next-open тесты пройдены.
- Новый процесс → полный повтор 7-дневного replay, включая curve и journal:
  **тождественное равенство** ранее сохранённому результату, не только совпадение PnL.
- Static credential-pattern scan всех изменяемых файлов: NO MATCHES (эвристика,
  не обещание обнаружить любой возможный секрет). В fixtures только явно DUMMY owner.
- Network-write scan новых execution harness/replay/evidence API: вызовов нет.
  Runtime evidence — только owner GET фиксированного локального отчёта;
  read/verify SHA не обращается к Service, Supabase или биржам.
- `ruff`, `mypy`, `bandit`, coverage, real Android/browser и реальный Supabase
  restart/open-close тест: **NOT RUN**. Инструменты optional lint отсутствуют.
  Никакого npm build нет: plain JS, новые зависимости не добавлены.
- FastAPI 0.115.12, httpx 0.28.1, websockets 15.0.1, pytest 8.3.5, numpy 2.2.6 —
  совпадают с requirements.txt. Transitive: pydantic 2.14.1, starlette 0.46.2,
  anyio 4.15.1.

Выполнены отдельные ручные ECC/Aura review passes по локальным guidance:
architecture, Python/FastAPI, security, trading math, testing/hidden errors.
Нативные ECC agents/plugin не запускались. Новые verification scripts проверены на
опасность `python -O`: генерация PASS запрещена при отключённых assertions;
для этого добавлен отдельный regression. Production execution не использует эти
verification assertions и не изменялся. Неполный месяц июль в 90-дневном отчёте
начинается **3 июля**, а не 1-го; месяцы не выдаются за одинаковые календарные окна.

Сравнение с Git tree базы подтверждает: существующие файлы изменены только
`app/main.py` (import/include router) и `static/index.html` (новая панель/assets).
Остальные существующие файлы, включая стратегии, движок, риск, SQL, scheduler,
Bybit/BingX/Bitget диагностики и старые исследовательские отчёты, байт-в-байт сохранены.

Файлы поставки:

- `app/main.py`, `app/execution_verification.py` — owner-only evidence route/wiring.
- `static/index.html`, `static/execution_verification.js`, `static/execution_verification.css` — отдельная панель доказательств, без торговых действий.
- `scripts/verify_auto42_execution.py` — изолированный production execution harness.
- `scripts/replay_auto42_verification.py` — точный offline replay и checkpoint/resume.
- `scripts/build_auto42_verification_report.py` — независимая бухгалтерская проверка и компактный evidence artifact.
- `tests/test_auto42_verification.py`, `tests/test_execution_verification_panel.py`, `tests/test_execution_verification_frontend.cjs` — regressions и safety.
- `docs/AURA_AUTO42_EXECUTION_VERIFICATION.md`, `docs/AURA_AUTO42_EXECUTION_VERIFICATION.json` — методика и воспроизводимые результаты.

Рекомендуемая production-проверка после deploy: сначала owner evidence panel,
затем наблюдение существующего журнала без изменения режима/параметров и без
искусственных сигналов. **Полный живой автономный open/close пока не подтверждён.**

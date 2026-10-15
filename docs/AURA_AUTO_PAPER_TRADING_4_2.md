> Обновление надёжности: см. `docs/AURA_AUTO42_RELIABILITY_FIX.md`. Базовые результаты тестов ниже относятся к первоначальной поставке 4.2; новые проверки указаны отдельно.

# Aura 4.2 — автоматическая виртуальная торговля

## Статус поставки

**NOT OPERATIONAL.** Код реализован и проверяется офлайн. Постоянная внешняя БД, её SQL/RPC, scheduler и live Render в этой сессии не настраивались и не проверялись. Деплой не выполнялся. Новая стратегия — **EXPERIMENTAL / NO_EDGE_FOUND**, не прибыльная по результатам исследования и не откалиброванная модель вероятности. Нового реального исторического или forward-прогона 4.2 нет; unit-fixtures не являются результатами торговли.

База: main `59587129132e034d00ee0c70360f98f61bf8641b` (Market Intelligence 3.2, Analogs 4.0, Forward Validation 4.1). Прежний Historical Pattern Auto Paper, Replay, балансы, риск-настройки, лаборатория, исторические отчёты и биржевые account readers сохранены. Этот режим использует **новый отдельный портфель**. Публикация коммита не является подтверждением обновления Render.

## Карта компонентов

- `app/automated/engine.py`: чистые Decimal-переходы, ledger accounting, sizing, SL/TP, loss gates, watermark.
- `app/automated/strategy.py`: фиксированный вариант `AURA_AUTO_PAPER_4.2.0` и проверка согласованного закрытого snapshot.
- `app/automated/storage.py`: отдельные таблицы, hash integrity, compare-and-swap revision, идемпотентность; Supabase либо локальная SQLite для разработки.
- `app/automated/service.py`: ограниченные scheduler ticks, owner-команды, recovery, fresh data gates.
- `app/automated/api.py`: owner GET/POST, CSRF, отдельная scheduler authentication; `/api/auto42/status`, `/control`, `/tick`, `/journal`.
- `scripts/auto42_schema.sql`: RLS, закрытые RPC, immutable event journal, account row lock.
- `.github/workflows/aura-auto42.yml`: внешний trigger, выключенный по умолчанию.
- `static/auto42.js`, `static/auto42.css`, секция в `static/index.html`: мобильная owner-панель.
- `tests/test_auto42.py`, `tests/test_auto42_frontend.cjs`: офлайн regression и интеграционные fixtures.

Переиспользуются `MarketContext` для общих Binance data/snapshot/MTF, существующие `research.market_intelligence.structure` алгоритмы, `app.lab.execution.fee/fill`, Decimal helpers и ограниченные async workers. Полный исследовательский simulator не используется как mutable live service: он требует весь исторический массив и стартовый баланс на каждый прогон. Новый небольшой переходный ledger использует его финансовые примитивы и изолированную транзакционную persistence. Обычный Paper DB не открывается. Replay/4.1 не получают новых mutation-вызовов.

## Замороженная экспериментальная стратегия

Символ BTCUSDT, базовый timeframe 15m. Только закрытые свечи, выбранный snapshot и raw history должны иметь один SHA256/source и последний UTC cutoff. 1h/4h должны состоять из полных закрытых UTC-блоков, иметь прогрев и актуальные confirmation timestamps.

Для LONG требуется retest LONG после подтверждённого BOS или CHoCH и направленного breakout на одной предыдущей confirmation timestamp, не старше 8 свечей. SHORT симметричен. EMA-направление всех 15m/1h/4h совпадает, ADX текущего frame ≥25, режим TREND_UP/TREND_DOWN соответствует направлению. Встречный или неоднозначный liquidity sweep блокирует вход. ATR положителен; отношение текущей волатильности к прошлой базе в [0.65, 2].

LONG stop = min(low retest-свечи, подтверждённый breakout level) − 1.5 ATR; SHORT симметрично через max(high, level) + 1.5 ATR. Target — расстояние 2R от signal close. Ближайший известный встречный support/resistance не должен находиться между signal close и target. Уровни используют существующие определения, включая явно описанный rolling50 fallback; BOS требует подтверждённого pivot и не равен rolling breakout. Алгоритмы определения структуры и пороги существующей Aura не изменены.

Сигнал сохраняется как pending в транзакции закрытой свечи. Ни аналоговые частоты 4.0, ни исходы 4.1 не используются для разрешения входа. Если условий нет — WAIT с причиной. Параметры фиксированы заранее, не оптимизировались по 2025 или другой истории.

## Исполнение и бухгалтерия

**Это closed-candle simulation, не intrabar tracking и не настоящий рыночный fill.** Уже сохранённый сигнал исполняется виртуально на open следующей 15m свечи, когда эта свеча закрылась и стала доступна для settlement. Запись журнала различает signal_at, entry_time и фактическое время записи события. Не применяется high/low сигнальной свечи к новой позиции. Нового сигнала на page load или на START нет: START ставит ACTIVATION_BASELINE; решение начинается на следующей новой закрытой свече.

Adverse slippage: **0.05% на каждый fill**. Комиссия: **0.10% за сторону**. Это прозрачные экспериментальные допущения, не заявление о фактическом тарифе биржи. Денежные значения Decimal, деньги округляются до 1e-8 USDT, quantity вниз до 1e-12 BTC, fees вверх.

LONG entry увеличивается на slippage, exit уменьшается; SHORT наоборот. Gross PnL = sign × (exit_fill − entry_fill) × quantity. Net PnL = gross − entry_fee − exit_fee. Entry fee списывается сразу, при закрытии баланс меняется на gross − exit_fee; проверяется invariant `balance = 10000 + realized_net − open_entry_fee`.

Liquidation equity = balance + unrealized fill-adjusted gross − hypothetical exit fee. Открытые unrealized суммы не считаются реализованной прибылью. Profit factor — сумма положительных net PnL / абсолютная сумма отрицательных net PnL; без losses undefined, без trades win rate undefined. Все metrics относятся только к текущей 4.2 epoch, не ALL старого Paper.

Gap через stop исполняется по неблагоприятному open. Gap через target — по target, без бонуса. Если внутри свечи затронуты SL и TP, выбирается stop, причина STOP_LOSS_AMBIGUOUS. Порядок intrabar-касания не выдумывается. SHORT — виртуальная линейная 1x модель по Spot ценам; funding, borrowing и настоящий margin account не моделируются.

## Риск и аварийные действия

Фиксированная политика отдельного портфеля:

| Настройка | Значение |
|---|---:|
| Начальный баланс | 10000 USDT |
| Риск на сделку | ≤0.5% liquidation equity |
| Позиции | максимум 1 |
| Notional | максимум 2000 USDT |
| Дневной лимит потерь | 2% от начального известного UTC-day equity |
| Общая просадка | 10% от peak liquidation equity |

Quantity ограничена risk budget, notional и виртуальным балансом; unit risk включает adverse stop slippage и обе fees. Перед next-open входом SL/TP повторно проверяются относительно нового fill; гэп, испортивший уровни или reward после расходов, отклоняет вход. Гэпы могут превысить плановый stop-risk: фактический убыток не обрезается ради красивого лимита. Лимиты запрещают последующие входы, но не гарантируют потолок реализованного gap-убытка.

Loss gates считаются на доступных opening/closed liquidation marks; intrabar equity path отсутствует. Дневная база переносится из последнего известного equity при смене UTC-day, без выдуманной midnight цены. Достигнутый дневной минимум сохраняется до следующего дня; достигнутый общий max drawdown сохраняется на всю epoch. Автоматического rearm после risk pause нет.

START — owner auth, CSRF header, явное подтверждение, актуальная revision и свежий coherent snapshot. STOP очищает pending и запрещает новые входы. EMERGENCY дополнительно ставит долговременный latch; rearm требует отдельного RESET после закрытия позиции. **Защитные виртуальные выходы после STOP/EMERGENCY продолжаются только внешними ticks на достоверных свечах.** Аварийная команда не выдумывает рыночную цену и не закрывает неизвестную позицию мгновенно.

RESET с отдельным подтверждением создаёт новую epoch OFF и сохраняет старый snapshot в архивном событии. При открытой позиции или ON сброс запрещён. Старые события не удаляются и не переписываются. STOP/EMERGENCY доступны без Binance и без scheduler token; при недоступной БД их запись невозможно подтвердить, UI показывает неизвестный исход.

## Scheduler, recovery и gaps

Нет in-process automation timer. GitHub Actions вызывает отдельный authenticated POST каждые 5 минут. Job выключен repository variable по умолчанию; настройки scheduler не активируют портфель. START делает только владелец.

Один tick ≤55 s, storage RPC ≤12 s, ограниченная concurrency и response size. Client disconnect не отменяет уже начатую bounded обработку. Persisted ON сохраняет ранее выданное owner-разрешение после restart; OFF остаётся OFF. Candle watermark, pending, позиция, accounting и decision events коммитятся атомарно с revision-CAS и row lock. Повтор одного tick/candle/request не создаёт повторную позицию. Уникальность signal/OPEN связана с epoch и timestamp.

START не повторяется автоматически после конфликтующей STOP-команды: revision защищает даже от поздней доставки HTTP. Emergency можно нажать во время pending UI запроса; поздний ответ не перерисовывает старый режим.

Пропущенные 5-минутные slots и candles учитываются в state/journal. На пропущенных scheduler candles pending entry отменяется, исторические сигналы не восстанавливаются задним числом. Для уже открытой позиции разрешён последовательный защитный settlement до 32 достоверных contiguous свечей. При настоящем gap, source correction или слишком длинном sleep — PAUSED, без fake close/forward-fill. Открытая позиция остаётся неразрешённой; требуется отдельная проверка истории/восстановления владельцем. Автоматического обхода неизвестного интервала или ручного фиктивного close endpoint нет. Нехватка MTF запрещает вход, но не блокирует protective exit по coherent доступным ценам.

## Настройка владельцем — обязательна

Платные сервисы не создавались. Квоты Supabase/Actions/Render следует проверить самостоятельно. Можно использовать бесплатный отдельный Supabase project либо существующий project с изолированными auto42 tables/RPC; код не обращается к таблицам 4.1/обычного Paper.

1. В Supabase SQL Editor вручную выполните `scripts/auto42_schema.sql`. В sandbox PostgreSQL отсутствует: реальное SQL execution/RPC **NOT RUN**. До работы обязательно проверить load/commit/history, rollback, RLS, повтор tick и concurrency в выбранной БД. Доступ имеют только server service-role RPC; anon/authenticated запрещены.
2. Render Environment: `AURA_AUTO42_SUPABASE_URL=https://<project-ref>.supabase.co`, `AURA_AUTO42_SUPABASE_SERVICE_KEY` (server-only), `AURA_AUTO42_SCHEDULER_SECRET` (ASCII 32–256 символов). Scheduler secret должен отличаться от owner password, DB key и forward scheduler secret. Существующий `AURA_TESTNET_VIEW_PASSWORD` остаётся owner authentication. Биржевые credentials для 4.2 не требуются и не читаются.
3. GitHub Actions secrets: `AURA_AUTO42_TICK_URL=https://aura-traiding-terminal.onrender.com/api/auto42/tick` и `AURA_AUTO42_SCHEDULER_SECRET`. DB key/owner password в Actions не нужны.
4. Установите repository variable `AURA_AUTO42_ENABLED=true` после schema/env проверки. Запустите workflow_dispatch при портфеле OFF. Убедитесь, что run подтверждён, state сохранился после restart, duplicate не создаёт новых events и secrets отсутствуют в логах.
5. На Android откройте терминал → «АВТОМАТИЧЕСКАЯ ДЕМОТОРГОВЛЯ — 4.2» → «Вход владельца» → обновите состояние. Только после успешного smoke и fresh данных нажмите START PAPER и подтвердите. Наличие ON означает сохранённое разрешение, а не доказанную непрерывную работу.
6. Проверьте следующие реальные scheduler runs, signal/pending/entry и SL/TP. Стратегия может долго возвращать WAIT. Не ослабляйте фильтры ради получения сделки. STOP прекращает входы; scheduler можно оставить для protective exits. Для emergency используйте отдельную кнопку.

GitHub cron best-effort, не SLA: задержки, inactivity disabling и лимиты возможны; Render Free спит. «Недавний запуск подтверждён» не означает 24/7. Фиксированный workflow URL не поддерживает произвольные домены/redirects. Ошибки и retry ограничены и не включают headers/URL/секреты.

SQLite доступна только для разработки: `AURA_AUTO42_SQLITE_PATH=/some/local/path/auto-paper-42.sqlite3`. На Render отклоняется. Чужая DB или смешанная local/remote конфигурация отвергаются. Нет скрытого fallback после Supabase error.

## Журнал и аудит

Events append-only, raw JSON SHA256, account integrity check. Состояние — компактный snapshot, история — отдельные строки; UI читает последние 60 событий и полный journal постранично через owner `/api/auto42/journal?after=0&limit=100`. Metrics — всю текущую epoch, список последних сделок может быть неполным. Snapshot, pending, watermark и trades survive restart только при сохранённой БД. Смена/потеря внешней БД не является recovery: регулярные backups нужны отдельно.

SQL triggers/RLS не защищают от администратора БД, способного изменить schema. Сервисный ключ — доверенная серверная authority, должен храниться только в Environment. Transport/redaction reused из 4.1, POST allowlist ограничен тремя auto42 RPC в фиксированном Supabase HTTPS project. Ни один POST не направляется бирже. Новых зависимостей нет.

## Проверки, review и ограничения

Финальный полный Python suite: **1065 passed**, 1 предупреждение (54.92 s); новых Python-тестов: **44**. JavaScript: **151 passed**, 10 файлов; новых тестов: **11**. Python syntax: 150 файлов PASS; JavaScript/scheduler syntax и imports PASS. Artifact 4.0 совместим и byte-for-byte сохранён. Машинная сводка — `docs/AURA_AUTO42_VERIFICATION.json`. Используются все существующие offline Python и Node suites; тесты не отправляют ордера и не используют настоящие credentials. Сценарии включают LONG/SHORT, fee-inclusive sizing, gap/ambiguous stops, actual market-structure prefix invariance, closed MTF, restart, two-instance concurrency, stop/start races, emergency, persistence corruption, loss limits, owner/CSRF/scheduler auth, remote contract/error handling и mobile DOM interactions.

ECC используется как существующие instruction-only skills/checklists: архитектура/Python, code review, security review, testing/module-regression и trading math. Нативные ECC hooks/agents/CLI не запускались; отдельные review passes выполнены одним исполнителем. Исправлены подтверждённые review-дефекты: stale START после STOP, недоступная emergency во время UI запроса, MTF blocking protective settlement, несовпадение UI/API safety envelope, обработка malformed data и snapshot integrity. Production formulas не менялись.

**NOT RUN:** реальные Supabase SQL/RPC/durability, GitHub cron, Render deployment, Android Chrome/browser layout, реальная независимая forward-оценка стратегии. Ruff/mypy/bandit отсутствуют; вместо них выполнен ограниченный статический поиск secrets/endpoints и dependency/isolation review, без заявлений об эквивалентности полному security scanner.

Ручные проверки на Render/Android: ширина 320–430px и отсутствие overflow, owner login/logout, touch/keyboard controls, stale/wake status, timeout release, остановка во время START, restart с pending/open position, duplicate tick, midnight loss gate, SL/TP с записью costs, RLS и отсутствие exchange requests. Необходимо проверить setup на выбранной БД до unattended режима. Edge и прибыльность не подтверждены; автоматическая торговля реальными средствами невозможна в этом модуле.


Команды воспроизведения в обычной среде с requirements.txt:

```bash
python -m pytest -q
node --test tests/*.cjs
node --check static/auto42.js
python -c "import app.main"
```

В sandbox использовались уже доступные pinned dependencies из `/workspace/ecc-audit-deps` и test-only `scripts.replay_aura_csv.enable_sandbox_poll()` с отключённым pytest plugin autoload; runtime event loop не изменён. Версии соответствовали requirements.txt: FastAPI 0.115.12, uvicorn 0.34.2, httpx 0.28.1, pytest 8.3.5, websockets 15.0.1, numpy 2.2.6.

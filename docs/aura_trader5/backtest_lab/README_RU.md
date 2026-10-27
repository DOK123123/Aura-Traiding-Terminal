# Aura Backtest Lab 1.0

Отдельный offline runner: `research/manual_analyst_replay/`. Только BTCUSDT
Bitget USDT-M Futures. Не импортируется web-приложением, нет HTTP endpoint,
таймеров, сети, exchange client, БД, аккаунта или управления PAPER.

## Быстрый воспроизводимый запуск

Python 3.12, существующие зависимости Aura. VectorBT не нужен и не установлен.
Из корня репозитория:

```bash
python -m pytest -q tests/test_manual_replay_engine.py tests/test_manual_replay_data.py tests/test_manual_replay_runner.py
python -m research.manual_analyst_replay \
  --manifest /path/to/local-archives/manifest.json \
  --protocol docs/aura_trader5/backtest_lab/PROTOCOL.json \
  --output /tmp/aura-backtest-lab-new-directory
```

`INPUT_MANIFEST.json` содержит имена, SHA-256 и публичные URL **четырёх уже
существовавших** официальных архивов Bitget: 202606–202609. Для повторения положить
эти ZIP и копию INPUT_MANIFEST.json с именем `manifest.json` в отдельную локальную
папку. Получение публичных файлов — отдельная подготовка; runner **никогда** не
скачивает данные и не обращается к терминалу/production. Секреты не нужны.
Не менять ожидаемые хеши при несовпадении — расследовать новую редакцию источника.

Выходная папка должна быть новой. Повторный запуск не дописывает и не заменяет
существующий результат; можно воспроизводимо повторить в другой новой папке.
Запись во временную папку и rename после полного успеха; при ошибке временные
артефакты удаляются. В app/static/deploy/корень кода писать запрещено. В Render
(`RENDER`) и Cloudflare (`CF_WORKER`) runner отказывается запускаться.

## Входной контракт и качество

- Строгий manifest v1: `source=BITGET_USDT_FUTURES_BTCUSDT`, `symbol=BTCUSDT`,
  `product_type=USDT-FUTURES`, `data_kind=REAL_PUBLIC_ARCHIVE` либо явно
  `SYNTHETIC_TEST`. Source label не является криптографической аттестацией биржи.
- Native execution grid — 1m либо 5m, только epoch **seconds UTC**; milliseconds,
  пропуски, дубли, неупорядоченные времена, плохой OHLCV/объём запрещены. Никаких
  fake fills или заполнения пропусков искусственными свечами.
- `BITGET_OFFICIAL_MINUTE_ZIP`: точный BTCUSDT_UMCBL_1min_YYYYMM.zip, один
  одноимённый CSV, `timestamp/open/high/low/close/basevolume`. REAL ZIP требует
  официального HTTPS `img.bitgetimg.com`, без query/fragment. ZIP не извлекается
  в файловую систему. Ограничены размер, число файлов и строк; хеш до/после чтения.
- CSV/CSV_GZ: `time,open,high,low,close,volume`; источник задаётся проверяемым
  manifest, независимое происхождение сам CSV не доказывает.
- `availability_mode=OBSERVED` требует `available_at`: это время, когда закрытая
  свеча стала доступна наблюдателю, не время её открытия. При наличии received_at
  берётся более позднее значение. Доступность не ранее close и не позже +1h,
  монотонна; последняя доступность не позже manifest.asof.
- Для архивов реальное время публикации не сохранилось. Применяется честное
  `ASSUMED_CLOSE_PLUS_DELAY`, здесь **+2 секунды**. Это допущение, не наблюдение.
- 5m/15m/1h/4h **производные от одного minute Futures источника**, UTC-бакеты;
  только полные интервалы, OHLC и суммарный base BTC volume. Неполные крайние
  бакеты можно отбросить, внутренние пропуски нельзя. Не смешиваются Spot,
  другая биржа или trade-derived OHLC с архивными candles.
- Фиксированные 200 закрытых свечей каждого timeframe, как в нынешнем service
  ANALYST; warmup 4h требует примерно 33⅓ дня. Более ранние сигналы — WAIT/WARMUP.

Фактическая проверка: 175680 minute bars, 2026-05-31 16:00 — 2026-09-30 16:00 UTC
exclusive; дубликатов/пропусков нет. Месячные **имена** архивов имеют UTC+8
границы; числовые timestamps не сдвигались. Первая попытка остановилась с
PROTOCOL_RANGE до расчёта доходности, потому что первоначально предполагалась
UTC-граница 01.10. Конец исправлен по фактическим данным, параметры не менялись.
288 агрегированных 5m bars совпали по OHLCV с ранее сохранёнными public REST
ответами Bitget; новое сетевое соединение с Bitget/Render в этом задании не нужно.
См. `DATA_QUALITY.json`. Это выборочная сверка, не гарантия всего архива или SLA.
Publisher checksum отсутствует; хеши локальные, из предыдущей TLS-загрузки.

## Причинность и неизменный ANALYST

`adapter.py` вызывает **существующий** `app.aura_trader5_scenarios.assess`;
формулы, EMA/RSI/ATR/Fibonacci, условия входа и радиус подтверждения pivots не
изменены. В окно попадают лишь `available_at <= decision_time`; незакрытые/ещё
недоступные старшие свечи не используются. Будущее не влияет на prefix result.
Цена raw minute OPEN не используется при генерации сигнала, только в исполнении.

ID зависит от source/strategy/tick/5m close, не от хеша будущей части файла.
Расходные stress cases используют те же frozen signals. Повторный одинаковый ID
игнорируется, конфликтующие уровни под тем же ID блокируются. На каждую свечу
один сигнал, одновременно максимум одна позиция. Сигнал при существующей позиции
не откладывается для повторного открытия после её закрытия.

### Почему минутное исполнение

TTL ANALYST ограничен 60 секундами после анализа и ближайшим следующим 5m
закрытием. При publish +2s и latency +5s OPEN следующей 5m свечи уже прошёл,
а следующий ещё через 5 минут просрочен. **TTL не расширяется**: в 5m-execution
такой вход отклоняется. В минутной модели следующий open после +7s находится
на +60s и ещё в TTL (+62s). Это не гарантия достижимой цены: Bitget candle open
не является bid/ask, fill включает неблагоприятные модельные расходы и rounding.

## Модель исполнения и риска

- Начальный капитал каждого сегмента 10000 USDT, без плеча (1x обеспеченный
  linear USDT PnL), номинал ≤2000, риск ≤0.5% текущего cash balance после fees.
- Qty округляется вниз по lot. Tick/lot/min-qty/min-notional фиксированы
  протоколом; snapshot контракта есть, но их истинная историческая динамика
  неизвестна. Никаких реальных order constraints/account API вызовов.
- Сигнал исполнен не раньше `available_at+5s`, только на следующем допустимом
  execution open, пока не истёк TTL. И raw OPEN, и adverse fill должны попадать
  в исходную Entry-зону. SL/TP остаются **абсолютными** уровнями ANALYST.
- Fees 10 bps на сторону (консервативная модель исходного ANALYST), adverse
  slippage 5 bps + половина предположенного спреда 2 bps; tick adverse rounding.
  Это не обещание текущего персонального тарифа Bitget. Fees по filled notional,
  входной fee списывается при OPEN, выходной при CLOSE. Impact уже в price PnL,
  повторно не вычитается. Все денежные расчёты Decimal, 8 знаков USDT.
- Повторно проверяются геометрия и net R/R >=1.5 при фактическом modeled fill.
  Qty включает entry/stop fees и неблагоприятное исполнение; projected risk
  ограничен также остатком дневного и drawdown-бюджета. Нет отрицательной маржи
  при входе. Гэп всё равно может превысить плановый риск — убыток не обрезается.
- Минутные OHLC считаются после открытия позиции; нет pre-entry low/high fill.
  При одновременном касании — SL первым. Adverse stop gap по raw OPEN, favorable
  target gap не лучше самого TP. Нулевой объём не даёт входов/защитных fills.
- SL/TP — гипотетическая непрерывная защитная модель по minute OHLC, **не**
  воспроизведение Cloudflare/Render пяти-минутного scheduler или биржевые ордера.
  Точный intrabar порядок/ликвидность неизвестны; execution timestamps интервала
  условные. Он не доказывает, что production PAPER сможет исполниться так же.
- Дневной лимит 2%, глобальная просадка 10%. Guards наблюдают minute OPEN marks;
  дневная база — первый open UTC-дня, drawdown guard peak — ранее наблюдённые
  opens. При нарушении нет новых входов; защитный выход — следующий доступный
  open после latency. Global drawdown latch не сбрасывается до конца сегмента.
  Статистическая просадка использует **все** modeled opening/closing marks,
  включая gap. Будущий/ещё не опубликованный close не блокирует более ранний open.
- Конец сегмента: отдельный SEGMENT_END_LIQUIDATION_ESTIMATE — бухгалтерская
  оценка с последним close + exit costs, не гарантированный реальный fill.
- Funding **NOT_INCLUDED**: нет полной достоверной совместной истории funding и
  mark prices на выбранный период. Нельзя называть это net после всех расходов.

## Совместимость старого Strategy Lab

`app/lab/execution.py` не меняется. Независимые known-answer tests проверили
currency-neutral `fee`, `fill`, `metrics`, LONG/SHORT PnL и balance identity.
Используются **только эти** helpers и Decimal money/text. Полный `simulate`
**INCOMPATIBLE**: его relative stop_distance переносит SL/TP к новой цене
исполнения; нет availability/TTL, абсолютной entry-zone и нужных guards.
Регрессионный тест показывает перенос старым движком SL 95 →105 при next-open
110; новый сохраняет уровень 95. Это причина отдельного thin execution loop,
а не изменения Lab/Active43. Source-константа Binance Spot из Lab не используется
для маркировки данных. VectorBT по-прежнему не оправдан и не устанавливался.

## Протокол и результаты

`PROTOCOL.json` зафиксировал параметры, analyst source hash, 60/20/20, время
заморозки и ранее просмотренные календарные периоды **до вычисления PnL**.
Разбиение по календарю, окна прогрева используют только прошлое. Каждый сегмент
начинает с 10000, без переноса позиций через границы; нельзя складывать их
доходности и выдавать за continuous equity. Нет parameter search или настройки
на validation/test. Полный реестр просмотров не аттестован — он честно неполный.

Все три периода **NOT_INDEPENDENT**: reused calendar, заморозка после начала
истории, предположенное время доступности, отсутствие полного реестра.
Положительное число само по себе не меняет INSUFFICIENT_EVIDENCE.
Для действительно будущего test нужны prospective freeze, полное учётное
раскрытие exposure и новые наблюдения available_at/received_at; не новая биржа.

Артефакты результатов: компактный `summary.json`, `REPORT_RU.md`, `protocol.json`,
`decisions.csv`, `signals.csv`; по split/cost отдельные trades/events/equity CSV,
equity/drawdown SVG. Hash registry включает каждый файл. Полные metrics — по
полной кривой, не по прореженному изображению. Daily Sharpe, если вообще определён,
использует один последний mark на UTC timestamp; WR/PF/expectancy при пустой
выборке undefined, не 0% успеха. Baselines cash, full 1x Buy & Hold и capped
2000-USDT Buy & Hold с теми же расходами, но **другим риском**.

Стресс ×1.5/×2 масштабирует fee/slip/spread. Повторная проверка risk/RR может
изменить состав исполненных сделок, это не matched-trade cost attribution.
Restart — детерминированный новый replay от immutable inputs, не incremental
checkpoint/resume; два прогона идентичны, существующий output не перезаписывается.

## Ограничения и безопасность

Нет независимого подтверждённого преимущества, оптимизации или production
верификации. Тестовые LONG/SHORT сценарии синтетические и никогда не добавляются
к реальной исторической таблице. Runner не читает localStorage manual journal,
PAPER, Supabase, environment credentials или баланс действующего терминала.

По умолчанию max_rows=500000, 36 файлов, 128 MiB на файл/ZIP member, 512 MiB
сжатых входов; compute deadline 900s (настройка до1800s). Большие наборы требуют
локальной RAM и осознанного config; тяжёлые исследования не запускать в web.
Нет новых платных сервисов, миграций, фонового процесса и расписания.

Обязательные проверки: independent accounting, both sides/SL/TP/ambiguity/gap,
zero volume, margin/risk/remaining budgets, TTL, duplicate/collision, prefix,
late 4h, original analyst end-to-end, schema/checksum/limits, source hash freeze,
no network/app route, atomic output and deterministic rerun. Full Python/JS/CI
результаты записаны в отчёте доставки; skipped не считаются PASS.

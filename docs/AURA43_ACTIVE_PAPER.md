> АРХИВ: этот документ и `AURA43_TECHNICAL_VERIFICATION.json` описывают Spot
> реализацию коммита `6284a3c13da327be7ce69d8a85632571c32eab50`.
> Команды исследования воспроизводятся на том коммите. Текущий runtime —
> Bitget Futures v3, с другим namespace/источником/лотами. См.
> [актуальную инструкцию](AURA43_BITGET_OPERATIONS.md). Старые результаты не
> являются результатами Bybit и не подтверждают текущую production-сборку.

# Aura 4.3 Active Paper — реализация, исследование и запуск

**Исследовательский итог: NO_EDGE_FOUND. Режим выключен по умолчанию.**
Технически реализован отдельный автономный виртуальный портфель BTCUSDT. Ни одна из 15 конфигураций не подтвердила преимущество после расходов. Включение не является рекомендацией прибыльной торговли. Merge, deploy и production-сделки в этой работе не выполнялись.

## Основа и аудит существующей системы

Основа — актуальный main после PR #12/#13/#14, merge `0e7a721`. Draft PR #3–#11 и их зависимости не переносятся. Старый Lab используется только через уже принятые native indicators/strategies/metrics. Aura 4.3 Active — отдельный режим, не непринятая Aura 4.3 Adaptive из PR #3.

Проверены существующие Auto42 strategy/service/engine/storage, структура/MTF и closed-candle адаптер, Paper Practice, owner/CSRF API, публичные providers, Lab, GitHub/Cloudflare scheduler и frontend. Полный набор существующих тестов выполняется вместе с новыми.

Причина редкости Aura 4.2: одновременно требуются одинаковые EMA20/50 направления 15m/1h/4h, направленный retest исходного подтверждённого BOS/CHoCH за 1–8 свечей, ADX≥25, нужный regime, отсутствие встречной liquidity, volatility 0.65…2, свободная цель до противоположного уровня. На последнем проверенном main 90-дневном срезе: 4 LONG/0 SHORT, 3 закрытых сделки; 5009 первых отказов MTF и 3493 без retest; последние 30 дней без сигналов. Это не означает невозможность входа. PR #13/#14 уже исправили origin retest и protective recovery. Эти файлы и параметры здесь не меняются.

Существующий Paper Engine корректно рассчитывает оба направления, fee-inclusive размер, adverse slippage, SL/TP/гепы и Decimal PnL. Его open/close/fee/fill/mark/risk/validation переиспользованы. Исторический replay, успешный Practice и синтетический TEST_ONLY — разные доказательства; они не подтверждают production-сигнал Auto42. Supabase хранит состояние/журнал атомарно с CAS и уникальными ключами. GitHub cron best effort; ни ON, ни health=200 не доказывают 24/7.

## Архитектура нового режима

- `app/active43/strategies.py`: три существующих native Lab baseline + Pullback и Volatility Breakout; frozen protocol/config.
- `core.py`: сетево независимые переходы и watermark, существующая production Decimal бухгалтерия/риск, Spot lot-step адаптер, next-open execution, causal ATR trailing.
- `market.py`: только fixed-host public GET Binance Spot, ≤2 страницы/1300 свечей, 18s fetch/compute budget, worker thread для короткого live-расчёта. Полный backtest в веб-процесс не импортируется.
- `storage.py`/`active43_schema.sql`: только `aura_active43_*`, два новых append-only/account объекта и независимые RPC, SHA256, row lock/CAS, idempotency и SQL freshness OPEN.
- `service.py`/`api.py`: отдельный opt-in, owner/CSRF START/STOP/EMERGENCY и отдельный scheduler token. Нет API искусственного сигнала, ручного ордера, backtest, импорта аккаунта или reset.
- `evidence.py`: пассивная корреляция настоящих SIGNAL/OPEN/UPDATE/CLOSE. Ошибка диагностического кода не блокирует SL/TP; синтетика/локальные циклы не могут установить production proof.
- Отдельная мобильная панель, immutable historical comparison/equity и скачивание исторических сделок. История текущего Paper читается только из его Supabase namespace.

Внутреннее `state.version=AURA_AUTO_PAPER_4.2.0` — ABI переиспользованной бухгалтерии, не идентификатор стратегии. Отдельные `scope=AURA43_ACTIVE_PAPER`, `strategy_version=AURA_4.3_ACTIVE_PAPER_1`, ACTIVE43 epoch и pinned config/policy hash обязательны при каждом чтении/commit. Trade events явно помечены Aura 4.3. Несовпадение конфигурации блокирует исполнение, а не сбрасывает портфель.

## Формализованные гипотезы

Все параметры зафиксированы до просмотра результатов; оптимизация не выполнялась. Все семейства проверены на 5m, 15m и 1h. Торговый config фиксируется до final test.

| Семейство | Условия и техническое обоснование |
|---|---|
| EMA + RSI + ADX | EMA20/50, RSI≥55 LONG / ≤45 SHORT, ADX≥25 и соответствующий DI. Гипотеза сохранения тренда с импульсом. Выход при смене EMA/RSI/ADX. |
| Donchian + ATR | Close за предыдущими 20 high/low; обратный канал 10 для выхода. Фильтр ATR: положительный конечный ATR и положительная цель после расходов/допустимый SL/размер; отдельный подобранный volatility threshold не добавляется. Проверяемая гипотеза продолжения подтверждённого пробоя. |
| Trend Following + ATR | EMA50/200 и close относительно EMA50; exit при потере тренда. ATR trailing 2×ATR, начальный SL 2×ATR / TP 4×ATR. Гипотеза удержания движения с подтягиванием защиты. |
| Pullback | EMA20/50, ADX≥20, RSI≥50/≤50; предыдущая свеча касается EMA20, текущая направленно закрывается за её high/low и EMA. Гипотеза возобновления тренда после отката. |
| Volatility Breakout | 20-bar range, предыдущий ATR≤0.8 среднего 20 ATR, объём≥1.2 предыдущего среднего, подтверждённый close за диапазоном. Гипотеза расширения после сжатия, без заявления о доказанной эффективности. |

Для всех исходные расстояния SL/TP — 2/4 ATR. Уровни фиксируются по закрытой сигнальной свече; не пересчитываются задним числом к будущей цене. Некорректный следующий open относительно уровней отклоняется. Это отдельные стратегии, без изменения MTF/ADX Aura 4.2.

## Рыночные данные и честность проверки

Официальные Binance Spot BTCUSDT 5m monthly ZIP + отдельно полученные официальные CHECKSUM по HTTPS. 14 месяцев Aug 2025…Sep 2026 дают 122688 непрерывных 5m свечей с прогревом для 1h. 15m/1h — только полные UTC-блоки исходных 5m. Никакого Bybit Futures/подмены биржи/синтетического заполнения пропусков. Microsecond archive timestamps нормализованы и close_time проверен. Все URL/архивные SHA/CSV SHA — в public research JSON.

**Цена Spot и виртуальный SHORT не являются futures-данными или реально исполнимым Spot short без займа.** Funding, borrow, margin/liquidation и order-book/latency не выдумываются; они не моделируются. Архивные OHLCV — финальные снимки, не point-in-time история биржевых ревизий. Lot/notional ограничения — frozen текущие Spot reference, а не восстановленный исторический exchangeInfo.

Годовой период `[2025-10-01, 2026-10-01)` UTC:
- Development: 219 дней до 2026-05-08, 60%.
- Validation: 73 дня до 2026-07-20, 20%.
- Final OOS: 73 дня до 2026-10-01, 20%.

Каждый сегмент получает одинаковые 10000 USDT и отдельное плоское начальное состояние. Отдельный full-year run начинается с 10000 один раз; суммы сегментов не выдаются за его доходность. В конце исследовательского сегмента позиция закрывается с издержками как HISTORICAL_SEGMENT_END; в production такой сигнал/форсированное закрытие не создаётся.

Подбор победителя читает только development/validation: ≥20/10 сделок, положительный net и PF>1 на обоих сегментах; сравнивается худший сегмент и drawdown. Никто не прошёл. Donchian 15m — заранее объявленный fallback для технического исполнения, **не лучший прибыльный вариант**. OOS не меняет выбор.

Expanding walk-forward выполнен внутри первых 60%: обучение до дней 120/150/180, выбор только по уже закрытым сделкам прошлого префикса, следующие 30 дней отдельно. Validation/final test не возвращаются в обучение. Параметры фиксированы во всех folds.

**Ограничение независимости:** эти календарные периоды пересекаются с прежними исследованиями проекта. Это chronological OOS нового frozen протокола, не pristine project-wide holdout. Требуется новый настоящий forward-период. Ни положительный backtest, ни число сделок не объявляются доказательством прибыли; здесь все 15 OOS отрицательны.

Live и исследование используют одинаковое окно: UTC-дата **закрытия** текущей свечи минус 1000 свечей. Дневные causal prefixes эквивалентны native live анализу. Исправлена обнаруженная на разработке граница midnight; тест сначала воспроизвёл её на 5m/15m/1h, затем прошёл. Исправлена также JSON-сериализация Decimal расстояния trailing. Параметры не подбирались по результатам; итоговые прогоны пересчитаны после технических исправлений.

## Сравнение после расходов

Ниже full-year run с лatching risk stops. В неделю — на весь календарный год, включая паузу после лимита. OOS — независимый по текущему протоколу старт 10000, не продолжение остановленного годового счёта. Полные Win Rate, средняя прибыль/абсолютный убыток, duration, fees ratios, Sharpe assumptions, LONG/SHORT и все сегменты доступны в `static/active43-research.json` и таблице интерфейса.

| Стратегия | TF | Сделок | В неделю | Net USDT | Return % | PF | Max DD % | Fees USDT | OOS сделок | OOS Net USDT |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DONCHIAN | 5m | 169 | 3.24 | -1005.36 | -10.05 | 0.28 | 10.05 | 674.74 | 158 | -999.43 |
| TREND_ATR | 5m | 160 | 3.07 | -900.86 | -9.01 | 0.09 | 9.01 | 639.63 | 31 | -202.56 |
| EMA_RSI_ADX | 5m | 189 | 3.62 | -993.34 | -9.93 | 0.36 | 10.01 | 751.83 | 146 | -1006.41 |
| PULLBACK | 5m | 243 | 4.66 | -1000.84 | -10.01 | 0.53 | 10.03 | 969.98 | 154 | -1000.98 |
| VOLATILITY_BREAKOUT | 5m | 132 | 2.53 | -694.11 | -6.94 | 0.32 | 6.98 | 527.84 | 29 | -176.72 |
| DONCHIAN | 15m | 197 | 3.78 | -999.66 | -10.00 | 0.52 | 10.12 | 786.34 | 183 | -998.21 |
| TREND_ATR | 15m | 203 | 3.89 | -994.42 | -9.94 | 0.38 | 10.09 | 807.54 | 149 | -1002.86 |
| EMA_RSI_ADX | 15m | 228 | 4.37 | -994.59 | -9.95 | 0.59 | 10.05 | 907.69 | 165 | -1010.11 |
| PULLBACK | 15m | 207 | 3.97 | -894.30 | -8.94 | 0.65 | 10.01 | 826.21 | 111 | -663.15 |
| VOLATILITY_BREAKOUT | 15m | 82 | 1.57 | -410.64 | -4.11 | 0.52 | 4.11 | 327.80 | 13 | -36.88 |
| DONCHIAN | 1h | 120 | 2.30 | -848.27 | -8.48 | 0.60 | 10.03 | 477.98 | 73 | -388.22 |
| TREND_ATR | 1h | 190 | 3.64 | -871.41 | -8.71 | 0.62 | 10.07 | 752.98 | 168 | -995.84 |
| EMA_RSI_ADX | 1h | 255 | 4.89 | -866.53 | -8.67 | 0.79 | 10.16 | 999.14 | 56 | -276.66 |
| PULLBACK | 1h | 178 | 3.41 | -814.36 | -8.14 | 0.78 | 10.15 | 702.14 | 35 | -477.62 |
| VOLATILITY_BREAKOUT | 1h | 40 | 0.77 | -182.39 | -1.82 | 0.71 | 2.89 | 159.78 | 10 | -122.75 |

Donchian 15m: 197 закрытых сделок (100 LONG / 97 SHORT), 3.778/неделю, −999.65624160 USDT (−9.99656242%), Max DD 10.11934532%, PF 0.51657239, expectancy −5.07439717 USDT; комиссии 786.33872706 и slippage 393.16940766 USDT. OOS: 183 сделки, −998.20719492 USDT (−9.98207195%), DD 10.03240058%. **Для поиска доходности ни один вариант к Paper не рекомендован.** Технический режим можно отдельно проверять только как явно убыточный исторически виртуальный эксперимент.

Комиссия 0.10% и slippage 0.05% на каждую сторону — одинаковые frozen assumptions, не фактически измеренная комиссия конкретного аккаунта. Lot 0.00001 BTC, minQty 0.00001, minNotional 5 USDT, tick reference 0.01; публичный exchangeInfo проверяется с кешем до 24 часов; frozen lot/notional ограничения не обновляются автоматически. Изменение фильтров блокирует входы до review, не меняет модель автоматически.

Sharpe: UTC daily liquidation-equity returns, sample stdev, sqrt(365), zero RF; null при недостаточной выборке/нулевой variance. Expectancy — средний net закрытых сделок. Average loss — положительная абсолютная величина. Fees/abs gross и fees/abs net могут превышать 100% и не определены при нулевом знаменателе.

## Риск и исполнение

- Отдельные 10000 виртуальных USDT, ≤0.5% fee-inclusive planned stop risk, ≤2000 notional, одна позиция **в портфеле Active43**. Aura 4.2 имеет собственный независимый счёт.
- Начальные уровни от закрытого сигнала; next available candle OPEN, учёт после закрытия этой свечи. Это существующая closed-candle virtual settlement модель, не исполнение реальной заявки в момент HTTP-запроса.
- Gap SL — adverse open; TP gap — консервативно по цели. При SL/TP одной свечой первым считается SL.
- ATR trailing хранится отдельно от initial SL и вступает в действие после закрытия, без retroactive hit на том же low/high.
- 2% дневного убытка / 10% drawdown запрещают новые входы. Это триггеры остановки, не обещание абсолютной границы PnL: gaps, fees и открытая позиция могут дать превышение (оно отражено в метриках). Risk stop остаётся latched до явного owner review/START; дневной лимит можно возобновить только в новый UTC-день, без сброса баланса. Drawdown 10% и Emergency не обходятся START и автоматически не снимаются; нового баланса или reset этот API не создаёт.
- Каждые watermark, balance, события и tick key сохраняются одной SQL-транзакцией. Row lock/CAS + unique id защищают разные процессы. Потеря HTTP-ответа не означает успех; retry сначала читает состояние/receipt.
- Дополнительная SQL-проверка по времени БД не позволяет OPEN устаревшей свечи после задержки commit. Она не блокирует защитное закрытие по проверенной catch-up истории.
- Пропуск свечей удаляет старые pending entry/strategy exit, не создаёт задние входы и промежуточные trailing stops. Проверенная непрерывная история сопровождает старый SL; только актуальная свеча может дать новый forward-сигнал.
- Исправленный watermark bar / разрыв / watermark вне доступного окна ⇒ fail closed и owner review. Окно около 1000…1288 свечей, примерно 3.5–4.5 дня для 5m, 10.4–11.4 дня для 15m, 41.7–42.7 дня для 1h. Неизвестные пропущенные SL/TP не изобретаются.
- После рестарта читает тот же scope/config/позицию/режим. Новая установка OFF; ранее включённый режим восстанавливается по durable state, только со свежей проверкой.
- STOP/EMERGENCY запрещают новые входы, существующее сопровождение требует доступных данных, Supabase и внешнего scheduler. Read-only live quote/PnL не исполняют SL/TP и не меняют ledger.

## Проверки и доказательства

`tests/test_active43*.py/cjs`, существующие Python/Node tests, CLI `verify_active43_postgres` и machine report `docs/AURA43_TECHNICAL_VERIFICATION.json`. Финальные числа тестов и hash исходников — в machine report.

Настоящий локальный PostgreSQL 16: network none, без портов/DSN/production-ключей, 512 MiB/1 CPU, отдельная БД/роли. Production Service/Store/core/SQL RPC используются через mock HTTP bridge к настоящему psql, а не mock-БД. Это не hosted PostgREST или Render. Реальное время SQL helper проверено, затем только в одноразовой БД superuser подменяет clock helper контролируемым временем для исторического replay. Production SQL использует настоящий clock_timestamp; service_role не имеет права менять helper.

7 сценариев: LONG/SHORT × SL/TP/оба уровня + ATR trailing. Проверены intermediate UPDATE, рестарт БД/контроллера, конкурентные ticks, потерянный HTTP-ответ после настоящего CLOSE и отсутствие повторных комиссий. Независимый Decimal oracle проверяет fills/fees/slippage/net/balance.

8 групп: apply/reapply без изменения legacy, реальные RLS/anon/authenticated denial и service_role RPC, отсутствие сигнала, outage/recovery источника, свежесть OPEN по часам БД, SQL rollback после вставки событий, неизвестный исход OPEN exactly once, реально остановленная БД/restart и неизменность Aura 4.2/Practice. Точные названия проверок — в JSON. Два отдельно пересчитанных настоящих исторических LONG/SHORT также прошли Service → OPEN → UPDATE → restart → CLOSE → SQL.

Синтетические сценарии используются только офлайн. CLI не принимает production DSN/key и отказывается работать при RENDER. Проверены запреты owner/CSRF, отдельный scheduler token, нет искусственного signal/order/backtest endpoint, source-only public GET и отсутствие изменений существующих risk/execution файлов.

**UNIT_TEST_PASSED** и **BACKTEST_PASSED** означают успешную техническую проверку и завершённый расчёт, а не прибыльность. **PRODUCTION_PAPER_VERIFIED = FALSE** до реального Render/Supabase цикла. Пассивная live evidence коррелирует native public-data SIGNAL, OPEN, UPDATE, CLOSE с position/run/candle/source/Render SHA; локальная синтетика/история не квалифицируются.

## Локальное воспроизведение

Не загружайте production credentials в локальное окружение. Используйте зависимости requirements.txt и отдельную папку исследования.

```sh
python -m scripts.active43_history --folder /tmp/aura43-study
python -m scripts.research_active43 --folder /tmp/aura43-study --workers 2
python -m scripts.complete_active43_research --folder /tmp/aura43-study
python -m scripts.verify_active43_postgres --output /tmp/aura43-pg.json --history-folder /tmp/aura43-study
AURA_PRACTICE_VERIFY_POSTGRES=true AURA_AUTO42_VERIFY_POSTGRES=true AURA_ACTIVE43_VERIFY_POSTGRES=true python -m pytest -q
```

Обычный pytest без opt-in честно пропускает локальные Docker SQL-интеграции. В облачном sandbox используется только test-wrapper enable_sandbox_poll из существующего инструмента, production event loop не меняется. Docker должен быть локальным; CLI использует фиксированный Unix socket, pinned image и одноразовый container с guard label.

CLI сохраняет подробные trades/equity по отдельным файлам экспериментов, не огромным единым объектом. Fingerprint отвергает изменённый код/данные/протокол. Публикуются только bounded public summary, выбранная historical daily equity и compressed historical trades; это не аккаунт Supabase и не LIVE. Никакой scheduler для исследований и HTTP backtest API нет.

## Запуск владельцем на Render

1. Review Draft PR и тестов. Merge выполняет владелец отдельно; Render auto-deploy может сработать от merge, поэтому сначала проверить настройки. Эта работа не выполняла ни merge, ни deploy.
2. В SQL Editor существующей Supabase просмотреть и выполнить только `scripts/active43_schema.sql`. Он добавляет только aura_active43_*; существующие таблицы/балансы/сделки/ключи/roles не сбрасываются. Требуется существующий pgcrypto в extensions, как для работающей Auto42. Не переносить extension между схемами автоматически.
3. Задать новые Render env: `AURA_ACTIVE43_SUPABASE_URL`, `AURA_ACTIVE43_SUPABASE_SERVICE_KEY`, `AURA_ACTIVE43_SCHEDULER_SECRET`. URL/key можно взять у владельца для существующего проекта; не менять старые переменные. Key только серверный, никогда в браузере/Git. Scheduler secret ≥32 случайных символов, отличный от owner/service key/старых scheduler tokens. Используется существующий owner password `AURA_TESTNET_VIEW_PASSWORD`; его не менять.
4. Развернуть проверенный SHA вручную. Пока `AURA_ACTIVE43_ENABLED` отсутствует/false, новый режим не создаёт клиентов/счёт и не влияет на Auto42. После готовности владелец явно устанавливает `AURA_ACTIVE43_ENABLED=true`: первый портфель создаётся OFF; это ещё не START торговли. При повторном включении сохраняется существующий mode, reset не выполняется.
5. GitHub: новый repository secret `AURA_ACTIVE43_SCHEDULER_SECRET` с тем же значением; variable `AURA_ACTIVE43_SCHEDULER_ENABLED=true` для отдельного workflow. Старые Aura42 secrets, cron и Cloudflare worker не менять. Новый client имеет fixed Render URL; не использовать старый токен для нового endpoint. Никаких новых платных ресурсов не требуется, если текущих лимитов достаточно.
6. Войти владельцем и открыть AURA 4.3 ACTIVE PAPER. Проверить scope, config, OFF, реальный SQL CONNECTED/revision/saved_at, 10000 только для нового отдельного счёта; сверить, что старые балансы/позиции сохранены. Прочитать NO_EDGE_FOUND. Для чисто технического виртуального эксперимента явно подтвердить START EXPERIMENTAL PAPER. Нельзя считать выбранный fallback прибыльной стратегией.
7. Проверить реальные accepted scheduler ticks и watermark при закрытом браузере. GitHub cron best effort; бесплатный Render может спать. Нельзя выдавать это за 24/7. Частота нового job — 5 минут; поздние/пропущенные вызовы могут отменять pending, особенно на 5m. Никакие отсутствующие свечи/сигналы не подменяются.
8. Ждать настоящий подтверждённый сигнал. Сигнальная свеча лишь сохраняет pending; OPEN учитывается после закрытия следующей свечи с её open/slippage. Проверить одну позицию, actual entry/SL/TP/size/fees, затем updates и закрытие по SL/TP или next-open strategy exit. Не использовать Practice/TEST_ONLY для production evidence.
9. Сверить journal и SQL ниже; position ID/SIGNAL timestamp/source hash/Render SHA должны совпасть, OPEN/CLOSE не дублируются, баланс равен начальному + net − fee открытой позиции. Рестарт Render проверяется владельцем с сохранением revision/position/mode. Hosted PostgREST, реальные env и uptime здесь не подтверждены.
10. Для остановки новых входов использовать STOP, сохранив ENABLED и внешний tick до закрытия позиции. Не выключать весь режим/scheduler при открытой позиции: мониторинг остановится. Emergency автоматически не снимается, risk stop не сбрасывается ради продолжения. Для rollback сначала запретить входы, проверить отсутствие позиции, затем отключить новый job/feature и развернуть предыдущий SHA. Новые таблицы/историю не удалять.

```sql
-- READ ONLY, выполняет владелец. Не публикуйте частные результаты текущего счёта.
SELECT revision,saved_at,payload::jsonb->>'scope' AS scope,
       payload::jsonb->>'strategy_version' AS strategy_version,
       payload::jsonb->>'mode' AS mode,payload::jsonb->'config' AS config,
       payload::jsonb->>'balance' AS balance,payload::jsonb->>'realized_pnl' AS realized_pnl,
       payload::jsonb->'position' AS position,payload::jsonb->'production_cycle' AS cycle
FROM public.aura_active43_account WHERE id=1;

SELECT seq,kind,to_timestamp(created_at) AT TIME ZONE 'UTC' AS utc,payload::jsonb->'payload' AS details
FROM public.aura_active43_events
WHERE epoch=(SELECT payload::jsonb->>'epoch' FROM public.aura_active43_account WHERE id=1)
  AND kind IN ('SIGNAL','OPEN','POSITION_UPDATE','STOP_UPDATE','CLOSE','ERROR')
ORDER BY seq DESC LIMIT 100;
```

## Стоимость, хранение и ограничения

Новый worker/платный API/проект БД не создаётся. Тяжёлое исследование выполняется только локальным CLI (≤2 workers), не на Render. Live-анализ ограничен примерно 1000 свечами одной стратегии; UI historical summary около 230 KiB, trades gzip около 31 KiB, streaming static serving. Тестовая PG-конфигурация 512 MiB/1 CPU не является измерением потребления production Render.

Исследования воспроизводимы из Git config + публичных архивов/checksums. Данные текущего Active43 портфеля сохраняются в Supabase, а не ephemeral диске Render. Локальный PostgreSQL restart подтверждён; actual Render/Supabase recovery и резервное копирование облачной БД проверяет владелец. Бесплатные PITR/backups не предполагаются. Append-only журнал растёт: необходим контроль доступного места/egress/free quotas; использование и дополнительные расходы текущего проекта неизвестны. Автоматической очистки/удаления истории нет.

Namespace/RPC/code isolation не превращает широкий Supabase service_role key в credential с правами только одной таблицы. Серверный key остаётся секретом владельца; существующая модель доверия не меняется. RLS/anon/authenticated закрыты, client не получает key, приложение вызывает только новый allowlist RPC.

Не подтверждены production deployment, hosted PostgREST/JWT gateway, secrets/config текущего Render, непрерывность GitHub/Cloudflare, реальные forward OPEN/CLOSE. Приватная production Supabase не использовалась. Для подтверждения автономии нужен отдельный естественный native Render/Supabase cycle после ручного запуска владельцем. Убыточные исторические результаты не маскируются техническими тестами.

## Реальные исторические примеры SQL-цикла

Это изолированные исторические проверки с отдельным стартом 10000, не текущие сделки Render. Для аудита выбран первый закрытый LONG/SHORT с промежуточным update; никаких новых сигналов не подставлялось.

| Направление | Signal UTC | Entry | Размер BTC | SL | TP | Закрытие | Net USDT |
|---|---|---:|---:|---:|---:|---|---:|
| LONG | 2025-10-01T04:30:00+00:00 | 114644.803755000000 | 0.01744 | 114156.8417333258104 | 115448.8165333483792 | STRATEGY_EXIT_NEXT_OPEN | -11.75380417 |
| SHORT | 2025-10-03T02:00:00+00:00 | 119815.782140000000 | 0.01669 | 120409.57332414245010 | 118808.01335171509980 | STOP_LOSS | -14.92555876 |

## Финальный regression / review

**1360 Python PASS** (221.85 s), включая все три opt-in локальные PostgreSQL-проверки Auto42/Practice/Active43. **18 JavaScript-наборов PASS**, новый frontend — 12 тестов. 221 Python-файл проверен синтаксически, app.main импортирован; JS syntax PASS. Одно существующее предупреждение Starlette/AnyIO. Chromium 430 px: панель 406 px, owner START и таблица 15 моделей/equity PASS, ноль сделок; это явно офлайн UI-тест с MemoryStore/тестовой котировкой, не Supabase/Render.

Выполнены отдельные code review и security review по docs/ecc/TRADING_REVIEW.md: causal prefixes/UTC, unchanged risk/cost helpers, scope/namespace, атомарность/CAS/unknown outcomes, авторизация/CSRF, secret separation/redaction, public GET allowlist, SQL freshness/roles, bounded workers и отсутствие реальных ордеров. Нерешённых critical/high code findings не обнаружено. Credential-pattern scan охватывает изменённый текст и распакованный public historical artifact; реальных ключей нет. Риски инфраструктуры/исполнения/NO_EDGE перечислены выше.

**TECHNICAL_READY = TRUE**

**UNIT_TEST_PASSED = TRUE**

**BACKTEST_PASSED = TRUE** (проверка расчёта, не прибыльности)

**NO_EDGE_FOUND**

**PRODUCTION_PAPER_VERIFIED = FALSE**

# Aura Adaptive Intelligence 1.0

## Что реально работает

Добавлен отдельный owner-only экран **AURA INTELLIGENCE**: распознавание закрытых свечей, рыночный контекст, исторические аналоги, объяснение WAIT, каталог моделей, исторический replay, ручное предложение/подтверждение и отдельный виртуальный портфель. Реальная цепочка исполнения проверена на Binance-format данных; интерфейс не является макетом.

Это **первая экспериментальная версия**, а не система с доказанной прибыльностью. Все 17 прежних исследовательских стратегий отрицательны после издержек. Они не активируются и не переименовываются в прибыльные.

**Главное ограничение:** на подготовленном replay ни один кандидат не прошёл консервативный критерий исторического преимущества. Selector возвращает WAIT. Для проверки механики разрешён только **отдельно включаемый владельцем ручной эксперимент при WAIT**, после создания гипотезы и второго подтверждения. Он явно помечен как НЕ рекомендация; historical statistics/WAIT не подменяются положительным сигналом. Без этого opt-in сервер отвергает такой план. Это осознанное отделение исследовательского входа от рекомендации, а не снижение статистических порогов ради демо.

## Архитектура и границы

| Файл | Назначение |
|---|---|
| `app/intelligence/patterns.py` | Каталог, версии, чистые детекторы, `register(pattern, detector)` для новых code-owned моделей |
| `app/intelligence/analysis.py` | Причинные признаки, past-only matching, uncertainty, context и experimental selector |
| `app/intelligence/service.py` | Проверенный компактный dataset, SQLite-сессии, TTL, последовательное подтверждение и replay portfolio |
| `app/intelligence/api.py` | Owner/CSRF защищённые локальные API; live только read-only |
| `app/intelligence/data/demo.json` | Компактная реальная история и индекс; полный шестилетний архив на Render не нужен |
| `scripts/build_intelligence_demo.py` | Офлайн пересборка из проверенных архивов, без обучения по 2025 |
| `static/intelligence.{js,css}` | Русский мобильный экран и графические отметки |
| `tests/test_intelligence.py`, `tests/test_intelligence_frontend.cjs` | Offline regression и реальный end-to-end replay |

Новые модели регистрируются через единый callable интерфейс без изменения execution engine. Нет автозагрузки кода из ZIP, runtime plugins, hooks, private exchange clients или MCP. Каталог расширяемый, а не притворно полный список всех моделей.

Обычные Paper/Auto портфели не используются. Переиспользуется **существующий `app.lab.execution.simulate`** — Decimal next-open engine. Его код в этой задаче не менялся. `app/main.py` только подключает новый router. Existing pattern strategy, risk controls, Bybit/Binance read-only, market pipeline и предыдущие отчёты сохранены.

## Каталог и определения

Реально работают **21 свечная модель**:

- Hammer, Hanging Man, Inverted Hammer, Shooting Star;
- Doji, Long-legged Doji, Dragonfly Doji, Gravestone Doji;
- Bullish/Bearish Engulfing, Bullish/Bearish Harami, Harami Cross;
- Morning/Evening Star, Morning/Evening Doji Star;
- Marubozu, Spinning Top, Inside Bar, Outside Bar.

Контекст reversal-моделей не игнорируется: Hammer после снижения, Hanging Man после роста; противоположные контексты Inverted Hammer/Shooting Star; engulfing и harami требуют направленного предшествующего движения. Контекст в v1 — изменение close за четыре предыдущих свечи, а не субъективное распознавание тренда. Doji body ≤10% range; spinning top 10–30% с обеими тенями; hammer family body 10–35%, основная тень ≥2 bodies, противоположная ≤0.5 body; marubozu body ≥90%. Для звёзд используются три свечи, маленькое среднее тело, восстановление через midpoint первой и предыдущий тренд. В непрерывном crypto рынке строгий overnight gap не требуется; это документированная адаптация, не textbook stock-market идентичность.

**9 EXPERIMENTAL**: EMA alignment, ADX strength, volume spike, ATR compression/expansion, prior-20 breakout, confirmed swing high/low и three-bar FVG. Свинги подтверждаются только после двух уже закрытых правых свечей; timestamp означает момент подтверждения, а исходное pivot time указано в evidence. FVG — формальная непересекаемость первого и третьего бара; термин SMC неоднозначен, profitability не утверждается.

**43 PLANNED** имеют `algorithm:null`, не возвращаются как детекции: сложные свечные комбинации, Double/Triple Top/Bottom, H&S, triangles, flag/pennant/wedge/channel/cup, retest/false breakout/pullback, BOS/CHoCH/sweep/equal highs/order block и RSI/MACD divergence. Они требуют формализации допусков, подтверждённых pivot и отдельных fixtures. Нет mock-детекторов, выдуманных confirmations или fake scores.

Каждый результат содержит timestamp, symbol, timeframe, ID, direction, parameters, confirmations, limitations и version. Нейтральные фигуры не становятся автоматически LONG/SHORT. Родственные модели не считаются независимыми голосами.

## История, признаки и статистика

Compact pack: **7 488 реальных 15m свечей** с 15 ноября 2022 до 1 февраля 2023; replay разрешён только в январе 2023. 1h/4h собираются только из полных UTC-бакетов. До выбранной даты доступен причинный прогрев; формирующиеся свечи не включаются.

Индекс содержит **1 312 завершённых гипотетических событий** из 2020–2022. 2025 holdout не используется для индексации или выбора параметров. Source archive SHA256: `61eeafddd5fd7d955a149030d08075959a47e4f66171c0f3fe0d6c08d496c50d`. Compact pack SHA256: `9390ab14a33f93570ac4b83f9f91387372bd950cb729581735a9e62fbf1f6249`. Проверены gap/quarantine правила прежнего импортёра; события не пересекают разрывы. Источник — предоставленные проверенные внутри архива Binance-format данные; независимое получение official checksum не выполнялось.

Признаки: pattern IDs, EMA spread/ATR, ADX, RSI, ATR/close, relative volume, расстояние до прошлого диапазона, timeframe и направление. Matching — фиксированная нормализованная дистанция и categorical overlap, порог 1.5, максимум 64 аналога. В выборку допускаются только события с `resolved_at < analysis timestamp`; outcomes, ещё неизвестные на тот момент, исключаются. Временной purge — минимум четыре дня между событиями.

Каждое событие имеет виртуальные SL 2%, TP 4%, horizon четыре дня и одинаковый Decimal cost/risk engine. Horizon exit — следующий open после закрытой horizon-свечи. Это новая фиксированная исследовательская гипотеза, не оптимизация прежних стратегий. Возвращаются sample count, wins/losses, TP-before-SL frequency, mean net, нижняя normal-approximation оценка среднего, Wilson bound win frequency и описательная sample curve drawdown. Последняя — сумма независимых uniform-notional событий, **не** доказанная доходность адаптивного портфеля.

Минимум 20 non-overlapping samples; при недостатке данных — INSUFFICIENT_DATA, при неположительной нижней оценке среднего — NO_EDGE, при неподходящем контексте — WAIT. Normal approximation, regime dependence, nearest-neighbor selection и multiple testing ограничивают доверие; частота не является гарантированной вероятностью будущей сделки. Проверенная независимая прибыльность отсутствует. Для live стратегия всегда WAIT/LIVE_VALIDATION_REQUIRED.

Реализованы лишь два экспериментальных семейства selector: Breakout и Trend Continuation плюс WAIT. Retest, Pullback, Mean Reversion, False Breakout и Reversal остаются запланированы. Нет самовольного выбора победителя по 2025.

## Подтверждение, риск и persistence

Состояния: DETECTED → ANALYZED → PROPOSED → CONFIRMED / REJECTED / EXPIRED → PAPER_EXECUTED. При WAIT ручная гипотеза создаётся только отдельным owner запросом, если opt-in установлен при создании сессии. Сам аналитический selector остаётся WAIT.

Без подтверждения никакой виртуальный вход не происходит. Подтверждённый план ждёт следующего **наблюдаемого** open, затем защищённый existing engine заново вычисляет размер и риск. Предварительная карточка — оценка по текущему известному close, а не обещание цены исполнения; искусственные OHLCV для quote или performance не создаются. Фактическая позиция и журнал показывают реальные replay fills. SL/TP, fees, slippage, planned R/R, quantity и risk возвращает backend. Expected net value — масштабированное описательное среднее аналогов, не прогноз.

Replay config: 10 000 USDT, fee 0.10% per side, slippage 0.05% per fill, risk ≤1%, notional ≤2000, max one position. Настройки отдельного replay фиксированы и не изменяют сохранённые обычные Paper settings. Противоположные SL/TP стороны, неподходящий risk/quantity и отсутствие следующей свечи блокируют действие. Неопределённая последовательность SL/TP — SL first; adverse gap stop и conservative TP gap сохранены. Виртуальный SHORT не утверждается доступным на реальном Spot.

Авторизация переиспользует existing owner: `aura`, переменная `AURA_TESTNET_VIEW_PASSWORD` (≥12 символов). Credentials не выводятся и не сохраняются. Все mutations требуют `X-Aura-Paper: local-only`, same-origin и проходят existing CSRF checks. Client не задаёт цену, risk, direction, mode или exchange endpoint при подтверждении. TTL 300 секунд и текущая replay candle проверяются сервером. `BEGIN IMMEDIATE` сериализует конкурирующие подтверждения; повторный confirm возвращает тот же результат. При продвижении неподтверждённый план EXPIRED.

SQLite: `.data/intelligence.sqlite3`, отдельно от Paper/Auto/Lab. Сохраняются confirmed inputs, состояния, journal и portfolio snapshot. Recovery перепроверяет dataset и software fingerprint, поэтому новая версия не переписывает прошлый PnL молча. На Render Free диск ephemeral: restart того же диска восстанавливается, замена инстанса/redeploy может потерять сессии. Не заявляется долгосрочная durability. До 20 сессий и 512 шагов на сессию; ошибки storage/history отображаются, баланс не выдаётся за настоящий счёт. При достижении конца dataset открытая позиция остаётся открытой, искусственного final fill нет.

API: `/api/intelligence/manifest`, `/catalogue`, `/live`, `/sessions`, `/sessions/{id}`, `/proposal`, `/decision`, `/advance`. Private exchange order endpoints отсутствуют. Live только public market reads через existing pipeline и timeout; подтверждение live сделки не реализовано.

## Реальный smoke scenario

`docs/AURA_INTELLIGENCE_SMOKE.json` содержит результаты на реальных закрытых свечах. Дата свечи: **2023-01-01 00:00 UTC**, timeframe 15m. Контекст EMA даёт SHORT, найденные паттерны доступны в analysis. 64 исторических аналога, отрицательное ожидание: selector WAIT/NO_EDGE. Тест явно разрешает ручную гипотезу и подтверждает её.

- Вход: 2023-01-01 00:15 UTC, реальный open 16521.26, adverse fill 16512.99937.
- Quantity: 0.121116700557 BTC; notional 2000 USDT.
- SL: 16843.41317; TP: 15852.17177.
- Выход: STOP_LOSS на наблюдаемой свече; fees 4.04103864 USDT.
- Realized PnL: **−45.07967723 USDT**, включая обе комиссии и slippage в ценах.

Это подтверждение работы цепочки и корректного отрицательного результата, не подбор прибыльного примера. Первая календарная дата replay фиксирована, будущий PnL не использовался для её выбора.

## Проверки и найденные проблемы

Доступные проверки: **81 Python unittest PASS** (19 новых плюс 62 прежних), **106 JavaScript tests PASS** (5 новых плюс 101 прежних). Python/JS syntax, import app.main, статический review credentials/private-write boundary выполнены. Реальный HTTP ASGI integration test проверяет owner/CSRF/create/plan/confirm/advance. Включены отрицательные случаи: нет opt-in/confirm, concurrent duplicate, expiry, forming/gapped candles, insufficient history, future outcome exclusion, risk refusal, missing dataset, restart. Все 21 свечные названия покрыты контекстными shape fixtures; experimental models проверены выборочно.

В sandbox asyncio thread wakeups первоначально зависли. Проверки повторены через **существующий diagnostic-only `enable_sandbox_poll`** в test runner; production event loop не изменялся. Полный legacy pytest suite NOT RUN: `No module named pytest`. Число непроверенных pytest cases не выдумывается. Chromium binary отсутствует, поэтому полноценный browser/Android test NOT RUN; mobile CSS, touch targets, labels и JS helpers проверены статически/Node. Live network, Render deployment и реальный Android не проверялись.

Исправления review: подтверждённый план не исполняется до следующего open; PnL/journal сохраняются отдельно; live переключение отключает старые replay controls; ошибка запроса убирает доступное подтверждение; последняя свеча без следующего open не допускает plan; исходная неполная risk-test fixture исправлена. Добавление router меняет hash `app/main.py`, поэтому старый native-reference source guard корректно отказывает в переиспользовании прежнего replay; regression test теперь проверяет именно этот отказ. Guard и старые JSON/Markdown отчёты не ослаблялись и не изменялись.

## Запуск и пересборка

Обычный запуск остаётся `python start_web.py` (0.0.0.0 и PORT). Compact pack входит в репозиторий, архив на Render не нужен. Пересборка производится офлайн:

```bash
python -B scripts/build_intelligence_demo.py /path/AURA_BTCUSDT_15m_2020-2025.zip /tmp/demo.json
# Проверить результаты и SHA; заменять data/demo.json + DATA_SHA только отдельным проверенным изменением.
node tests/test_intelligence_frontend.cjs
python -B - <<'PY'
from scripts.replay_aura_csv import enable_sandbox_poll
import unittest
enable_sandbox_poll()  # только если нужен workaround этого sandbox
r = unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tests', pattern='test_intelligence.py'))
raise SystemExit(not r.wasSuccessful())
PY
```

## Первый тест на Android

1. В Render дождитесь успешного deploy нужного commit. Здесь его фактический deploy не подтверждён.
2. Откройте **свой существующий адрес Aura** в Android Chrome; обновите страницу. Прокрутите до AURA INTELLIGENCE.
3. Нажмите «Вход владельца»: username `aura`, ваш существующий owner password. API keys для replay не нужны.
4. Нажмите «Открыть вкладку / загрузить историю». Увидите источник, SHA и дату; dataset недоступен — не продолжайте как будто он загружен.
5. Выберите 15m и **2023-01-01 00:00**. Это UTC open выбранной закрытой свечи; анализ доступен на её close 00:15.
6. Для данного smoke отдельно отметьте «Разрешаю ручное исследование гипотезы при WAIT» и нажмите «Создать отдельный replay». Убедитесь, что виден WAIT/NO_EDGE и обычный Auto Paper не активирован.
7. Нажмите «Сформировать план / ручную гипотезу». Просмотрите SHORT, оценочный entry, SL/TP, quantity, risk, costs и предупреждение. Без следующего действия позиция не откроется.
8. Нажмите «ПОДТВЕРДИТЬ» и подтвердите browser dialog. Статус сначала CONFIRMED, позиции ещё нет.
9. Нажмите «Следующая свеча» — появляется фактический virtual entry. Нажимайте «Вперёд на 32 свечи» до SL; результат должен совпасть со smoke PnL при той же начальной сессии.
10. Обновите страницу, снова откройте вкладку: сохранённая сессия восстанавливается, нового входа нет. Проверьте «ПРОПУСТИТЬ», expiry после пяти минут, WAIT без opt-in, landscape/portrait и ширину 320–430px.

Нерешённые задачи: полноценная независимая валидация новых hypothesis families, walk-forward и новые holdout периоды, более строгая uncertainty calibration, chart patterns/SMC/divergence, browser/Android validation и долговременный export/storage. Никакая новая стратегия не включена в production Auto Paper.

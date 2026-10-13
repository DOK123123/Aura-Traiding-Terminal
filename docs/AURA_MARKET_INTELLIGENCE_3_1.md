# Aura Market Intelligence 3.1 — мобильный анализ только для чтения

## Реализовано

В существующем AURA INTELLIGENCE добавлена вкладка **АНАЛИЗ РЫНКА**.
Исторический replay остаётся вкладкой по умолчанию. Новый экран показывает реальный
REST snapshot BTCUSDT на выбранном 15m/1h/4h: режим, HH/HL/LH/LL,
подтверждённые экстремумы, BOS/CHoCH, пробой/неудавшийся пробой/ретест,
liquidity sweep, ближайшие поддержку/сопротивление, ADX/RSI/ATR,
относительный объём, волатильность, экспериментальные FVG/order block и MTF.
Это описание рынка, **не торговый сигнал и не состояние Auto Paper**.

Решение всегда **WAIT / READ_ONLY / FORWARD_VALIDATION_REQUIRED**.
Нет новых кнопок исполнения, proposals или разрешений на сделки. Исполнение
нового режима, реальное и виртуальное, отключено. Старые replay API,
подтверждение владельца и портфели не изменены.

## Архитектура и границы

- `GET /api/intelligence/market-context?timeframe=15m|1h|4h`: существующий
  owner dependency из Paper, Basic username `aura`, существующий пароль владельца.
  Нет отдельного пароля/ключей. Пароль не задан — 403; неверный/отсутствующий вход — 401.
  `Cache-Control: no-store`, `nosniff`. Новый путь поддерживает только GET.
- `app/intelligence/market_context.py`: отдельный in-memory adapter,
  общий ограниченный refresh для трёх таймфреймов. Не использует Service replay,
  SQLite, Paper/Auto, приватных клиентов или research runner.
- Существующий `app.lab.data.public_page` — фиксированный public GET
  `https://data-api.binance.vision/api/v3/klines`, BTCUSDT/15m, без credentials.
  Транспорт не получает HTTP credentials владельца. Не меняется источник графика.
- `research/market_intelligence/structure.segment_states`: те же формулы 3.0;
  добавлен необязательный cooperative deadline, по умолчанию отсутствует.
  Бывшие `higher` и `split_parts` перенесены **дословно** в `app/lab/series.py`;
  старые research модули re-export их. Удалена цепочка импорта offline runner
  из runtime контекстного анализа. Формулы, параметры и прежние отчёты не изменены.
- `app/main.py`: создание/закрытие только этого adapter в lifespan;
  загрузка/вычисление происходят по защищённому GET, не при запуске.
- Новый frontend независим от `static/intelligence.js`; старый replay код
  неизменён, только обёрнут существующий HTML отдельной панелью вкладок.

Смена импорта меняет software hash будущего offline исследования: прежние
checkpoints не следует смешивать с новым source hash. Сохранённые результаты
Pattern Research 2.0 и Market Intelligence 3.0 не пересчитывались и не менялись.

## Реальные данные, причинность и свежесть

Запрашиваются 260 полных UTC-блоков 4h (4160 свечей 15m), плюс максимум
15 свечей после последней границы 4h: **не более 4175**. До пяти страниц,
не более 1000 записей и 1 MB тела на страницу; fetch timeout 12 s.
Проверяются 12 колонок REST kline, тип/выравнивание open/close time,
OHLCV, монотонность и дубликаты. Формирующаяся свеча исключается.
Дубликаты/плохие записи дают ошибку, а не сортировку/исправление.

1h/4h агрегируются только из полных 4/16 UTC 15m-блоков. Каждый таймфрейм
использует свои 250 непрерывных свечей прогрева. Gaps перечислены в JSON;
индикаторы и структура сбрасываются, пропуски не заполняются.
После нового разрыва 15m может восстановиться раньше 4h; неизвестный MTF
остаётся `null`, согласование не представляется подтверждённым.

Алгоритм pivots использует две свечи слева и две справа; timestamp экстремума
отличается от confirmation timestamp. Поиск MTF разрешает только
закрытия ≤ cutoff анализируемой свечи. Определения и подтверждения доступны
в JSON/раскрываемом разделе экрана. Структура/уровни относятся к выбранному
таймфрейму, MTF показывает 1h и 4h на его cutoff.

Вычисление в worker thread, cooperative deadline 8 s; все массивы ограничены.
Индикаторы тоже начинают историю на границе ограниченного окна: это ограничение
явно показано, точное совпадение со всей шестилетней EMA не обещается.
Ожидание HTTP response ≤22 s (12+8+2), один refresh task, TTL 30 s, rate-limit
с числовым Retry-After уважает серверный cooldown. Исходящие запросы не повторяются
бесконечным циклом. Ошибки сети/timeout/HTTP/403/451/429/неверных данных разделены.
В logs только разрешённый code; нет raw URL, upstream body или headers.

Свежесть пересчитывается на каждый GET, включая кэш: возраст закрытия должен
быть меньше интервала; базовый 15m age <900 s обязателен **для всех** кадров;
delivery age ≤90 s. Недоступный/устаревший snapshot не сохраняет старую структуру
как свежую. Ошибка источника заменяет кэш безопасным UNAVAILABLE.
На Android возраст продолжает увеличиваться относительно серверного age,
без доверия к часам телефона; отображение проверяется каждые 5 s. GET автообновляется
раз в 60 s только при открытой видимой вкладке, без параллельных повторов.
Смена timeframe отменяет/игнорирует старый ответ; новый запрос не может быть
отменён старым таймером. Запрос browser отменяется через 24 s.

## Аналоги и исследовательские результаты

**ANALOG_DATA_UNAVAILABLE**, совместимого verified compact pack 3.0 нет.
Replay 1.0 имеет другой вектор признаков/нормализацию/exit model;
его статистика не используется в новом анализе. Sample count, SHA, coverage,
exit model отсутствующего pack — `null`, не фиктивные нули.

В JSON представлены feature version `CONTEXT_VECTOR_1.1`, 21 feature definition,
adapter version `MARKET_CONTEXT_ONLINE_3.1`, несовместимость pack и ограничения.
Статическая историческая сводка 42 конфигураций/0 кандидатов имеет source report,
SHA256 и commit 7711696737630a69994eb37c81ac633874ad0fb4. Это метаданные
завершённого исследования, **не expectancy текущего состояния** (`null`).
2025 уже изучен, нового untouched holdout здесь нет. Для аналогов 3.0 нужен
отдельный проверенный компактный индекс с causal provenance, совместимыми
признаками, normalization/exit model и независимой forward-проверкой.
Их отсутствие не мешает текущему read-only анализу.

## Проверки и review

- Все доступные Python unittest: **180 PASS, 0 failures/errors/skips**;
  новые tests: **24**. Проверены full app ASGI, owner 401/403,
  новый GET, запрет POST, health/static, отсутствие вызовов replay Service,
  unconfigured Bybit без сети, closed candles, warmup, gaps,
  duplicate/order/OHLCV, no look-ahead, MTF границы, stale базовый поток,
  single-flight/cache, timeout/rate cooldown, редактирование ошибок,
  отсутствие account/execution/SQLite dependency.
- JavaScript: **116 PASS**, новые tests: **10**, включая DOM harness
  rendering, default/reload, клавиатуру, pending/obsolete responses,
  исчезновение старого анализа, read-only GET и мобильные CSS ограничения.
  Это offline DOM/CSS проверки, **не browser/device тест**. Playwright package
  доступен, но Chromium binary отсутствует; browser не запускался/не устанавливался.
- `python -m pytest -q`: **NOT RUN — No module named pytest**.
  24 старых pytest-модуля не импортируются без пакета; количество их
  parametrized cases не определено. Это не означает, что полный Python suite прошёл.
  Зависимости не устанавливались ради шаблонной проверки.
- AST всех Python, `node --check` всех static JS, `import app.main` — PASS.
- Architecture/security/market math review: нет связи нового режима
  с исполнением; переданы только закрытые валидированные bars; существующие
  formulas/fees/risk controls/Auto/replay не менялись. Анализ не рассчитывает
  PnL, sizing или вероятность сделки. Найденные frontend race с таймером и
  ложная свежесть 4h при старом 15m исправлены и покрыты regression tests.
  Custom static credential scan и read-only endpoint/import review — PASS;
  это не внешний pentest или полный анализ установленным security scanner.

С версии этого задания Python3.12.14, FastAPI0.141.1, Starlette1.6.0,
httpx0.28.1, numpy2.3.5; отличаются от некоторых requirements pins.
Без обновления зависимостей. ASGI tests используют существующий test-only
`enable_sandbox_poll()`, production event loop не изменён.

### Ресурсы и реальные проверки

На существующем **реальном историческом** проверенном replay dataset,
4160 bars: ~0.54 s, peak process RSS ~52 MiB, snapshot15m ~18 KB
в этой Codex среде. Это проверка алгоритма/ограничений, **не live источник,
не новый бэктест и не измерение полного Render процесса**. Archive/index
не читаются runtime adapter; web-запрос не импортирует offline runner.

Один public read-only REST smoke из Codex вернул **TIMEOUT**, без свечей;
успешная live связь с Binance не подтверждена. После timeout тестовый процесс
остановлен, поскольку sandbox resolver worker задерживал завершение процесса.
Новых сетевых попыток/обхода ограничений не делалось. Render transport/device
не проверены. **NOT_DEPLOYED**: фактическое обновление Render не запускалось
и не подтверждалось. GitHub push не означает проверенного deploy.

## Как открыть и проверить на Android

Адрес страницы: **ваш существующий Render URL + `/#market-analysis`**.
Имя Render сервиса в репозитории не задано (GitHub homepage пуст);
точный домен не выдумывается. Пример формы: `https://<ваш-сервис>.onrender.com/#market-analysis`.
Для локального запуска: `python start_web.py` и открыть тот же путь на своём
хосте. Новый порт/preview здесь не открывались.

После подтверждённого deploy:

1. Откройте существующий терминал в Android Chrome и найдите AURA INTELLIGENCE.
2. Нажмите «Вход владельца: aura», используйте существующий owner password,
   затем вкладку «АНАЛИЗ РЫНКА»/ссылку с `#market-analysis`.
3. Нажмите «Обновить анализ»; проверьте источник BTCUSDT, последнее закрытие UTC,
   freshness, 15m/1h/4h, nearest levels и время подтверждения событий.
4. После холодного старта/недоступности источника должен появиться понятный
   UNAVAILABLE/TIMEOUT/недостаточный прогрев; **не** старые зелёные данные.
   4h может быть UNKNOWN после gaps. Ничего не исполняется.
5. Сверьте закрытие 15m/1h/4h с внешним публичным графиком;
   на forming свечах анализ не должен меняться как подтверждённый.
6. На 320/360/390/430px проверьте перенос текста, отсутствие горизонтального
   overflow, нажатия ≥44px, раскрываемые определения и возврат к replay.
7. При повторных нажатиях/смене timeframe/уходе в фон не должно быть
   старого ответа на новом timeframe, дубликатов запросов или зависшего loader.
8. Аналоги должны быть явно недоступны, решение всегда WAIT. В новом режиме
   нет live BUY/SELL или подтверждения сделок. Старый replay и его manual
   confirmation должны работать как раньше, обычный paper-портфель неизменён.

## Воспроизводимые команды

```bash
python start_web.py
python -m pytest -q  # нужен установленный pytest; здесь NOT RUN
node tests/test_market_context_frontend.cjs
# все offline JS suites
for f in tests/*.cjs; do node "$f"; done
```

Доступный unittest suite с sandbox-specific test-only accommodation:

```bash
python -B - <<'PY'
import unittest
from scripts.replay_aura_csv import enable_sandbox_poll
enable_sandbox_poll()
suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
def walk(s):
    for t in s:
        if isinstance(t, unittest.TestSuite):
            yield from walk(t)
        else:
            yield t
all_cases = list(walk(suite))
missing = [t.id() for t in all_cases if isinstance(t, unittest.loader._FailedTest)]
print('NOT RUN, import-unavailable modules:', missing)
available = unittest.TestSuite(t for t in all_cases if not isinstance(t, unittest.loader._FailedTest))
r = unittest.TextTestRunner(verbosity=1).run(available)
raise SystemExit(not r.wasSuccessful())
PY
```

Нужны ручные Render/Android проверки; отсутствие analog pack и проверенной
live связи не скрывается и не разрешает исполнения.

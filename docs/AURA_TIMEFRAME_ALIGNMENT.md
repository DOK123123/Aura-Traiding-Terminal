# AURA 4.2 — проверка timeframe alignment

Дата проверки: 2026-10-16. Исходный репозиторий: DOK123123/Aura-Traiding-Terminal,
коммит `04438674acf9a795a0666f8e1f2718221e7a9ed8`.

## Вывод и границы доказательства

Для close **2026-10-15 22:00 UTC** историческая реконструкция тем же production
анализатором и исходной стратегией воспроизвела `MTF_NOT_ALIGNED`:
**15m UP, 1h DOWN, 4h DOWN**. Это законное несогласие направлений.
Дефект расчёта/выбора свечей, который постоянно запрещал бы alignment, не найден.
Пороги и условия стратегии не исправлялись и не ослаблялись.

Это **реконструкция**, а не прочитанный исходный production snapshot. Доступны
код main и публичная история Binance. Исходный снимок scheduler tick 22:12:36,
его source hash и SHA развёрнутого Render-коммита не предоставлены. Поэтому
тождество с конкретными входами того запуска пока НЕ подтверждено. Нельзя по
одной русской строке исключить устаревшие данные или иной deployed commit.
Панель после обновления сохраняет входы будущих фактических решений и устраняет
этот пробел наблюдаемости. Старое решение она не восстанавливает задним числом.

Публичные GET: `/api/health` → 200, `/api/auto42/status` без owner → 401 на
`https://aura-traiding-terminal.onrender.com`. Это не проверка состояния Supabase,
mode=ON или автономного цикла. Production tick/control, позиции и баланс не трогались.

## Точный путь решения

1. `app/automated/api.py`: защищённый POST `/api/auto42/tick` → `Service.tick`.
2. `app/automated/service.py`: `snapshot` → `snapshot_for_auto` → production
   `MarketContext.snapshot('15m')`; затем `strategy(value, bars, now)`.
3. `app/intelligence/market_context.py`: `fetch_window` запрашивает только
   Binance Spot `data-api.binance.vision/api/v3/klines`, BTCUSDT, 15m.
   `end=floor(now/900)*900`, `start=floor(end/14400)*14400−4160*900`;
   4160–4175 свечей, `endTime=end*1000−1`. Open timestamps в секундах внутри
   приложения, миллисекунды только на границе API. Проверяются точный close time,
   OHLCV, дубли и порядок. Формирующиеся строки не входят в окно.
4. `app/lab/series.py:higher`: только полные UTC-блоки 4/16 исходных 15m свечей;
   open первой, high=max, low=min, close последней, volume=sum. Неполные блоки
   отбрасываются. Разрывы сбрасывают прогрев; синтетического заполнения нет.
5. `research/market_intelligence/structure.py:segment_states`: **на каждом TF
   независимо** EMA20 и EMA50 по close. EMA20>EMA50 → +1; < → −1; = → 0.
   EMA имеет SMA-seed из первых N свечей, затем α=2/(N+1). Состояние доступно
   после 250 непрерывных свечей соответствующего TF и положительного ATR14.
   ADX14/ATR14/RSI14 используют существующие формулы `app/lab/indicators.py`.
6. `market_context.py:analyze_window` выбирает через `bisect_right` последнее
   известное состояние 1h/4h с close≤15m close и возрастом<собственного шага;
   проверяет принадлежность последнему непрерывному сегменту.
   `known_mask=3` означает, что известны оба старших TF.
7. Alignment: `mask == 3 and h1.direction == h4.direction == trend_direction != 0`.
8. `strategy.py:_evaluate` сначала проверяет свежесть, source/hash, текущий
   15m close, непрерывность и timestamps старших TF. Отсутствующий/устаревший
   старший TF → `MTF_UNAVAILABLE`. Затем `known_mask != 3` **или** ложный
   `mtf.alignment` → `MTF_NOT_ALIGNED`. Фронтенд `static/auto42.js` переводит
   именно этот код как «Таймфреймы не согласованы».

После alignment есть другие неизменённые фильтры: направленный retest,
соответствие его стороны тренду, ADX≥25, TREND_UP/DOWN regime, отсутствие
встречной/неоднозначной liquidity sweep, подтверждённые BOS/CHoCH+breakout с одним
timestamp в предыдущих 8 свечах, ATR/volatility ratio 0.65–2.0, защитный stop
1.5 ATR и target 2R, отсутствие близкого противоположного уровня.
RSI/MACD/volume сами по себе не являются условием alignment. ADX не задаёт знак
направления; его порог — отдельный, более поздний фильтр.

## Реконструкция 22:00 UTC

Время в таблице — **close**, не open свечи. 4h close 20:00 на оценке 22:00
корректен: следующая 4h свеча ещё не закрыта. Требование одинакового close
всех TF в 22:00 было бы ошибкой; такого требования в коде нет.

| TF | Close UTC | EMA20 | EMA50 | Направление | ADX14 | Свечей прогрева |
|---|---|---:|---:|---|---:|---:|
| 15m | 2026-10-15 22:00 | 82244.913170 | 81945.858325 | UP | 17.703233 | 4168 |
| 1h | 2026-10-15 22:00 | 81857.446920 | 82110.994574 | DOWN | 21.793228 | 1042 |
| 4h | 2026-10-15 20:00 | 82443.037038 | 82981.930035 | DOWN | 36.639628 | 260 |

Mask=3; production alignment=false; повторная проверка сохранённых направлений
даёт false. Нет отсутствующей истории/разрыва в реконструированном окне.
ADX15m также ниже 25, но стратегия до этого фильтра в данном случае не дошла:
точная первая причина отказа — alignment.

`fresh_at_evaluation` в offline replay — моделирование исторического cutoff,
а не доказательство свежести доставки реального запроса в 22:12:36.

## Панель фактического production-решения

**TIMEFRAME ALIGNMENT DIAGNOSTICS** в существующей странице; GET
`/api/auto42/alignment` с существующей owner-auth и `no-store`.

EMA/ADX/ATR/RSI берутся из того же вызова `segment_states`, а сведения о старших
TF копируются в момент выбора соответствующего `other` в `analyze_window`.
`strategy` вызывает прежнее тело `_evaluate` ровно один раз и добавляет снимок
входов/результата. Панель не вызывает market fetch, анализатор, tick или control.
Сравнение знака сохранённых EMA с сохранённым направлением — только аудит
согласованности входов, не другая торговая стратегия.

Снимок содержит open/close/expected close всех TF, направления, значения
индикаторов, mask/flag/actual condition, точную strategy reason, freshness при
оценке, sample counts, hash окна, hash кода и допустимый Render commit.
`decision_valid` относится **только к alignment input consistency**. Значение
null означает отсутствие достаточных доказательств/ошибку данных. Это не
подтверждение всех risk gates, исполнения, прибыльности или live open/close.

Снимок сохраняется в `last_alignment_evaluation` существующего account payload
одной атомарной записью с решением/событиями/водяным знаком. DECISION event также
содержит его в signal. Ошибки данных, дошедшие до strategy, сохраняют отдельное
свидетельство, не превращаются в alignment rejection. Если upstream не дал
strategy входов, остаётся предыдущий снимок с прежним временем; рядом показаны
актуальные last_error/last_decision. Ошибка или отсутствие свежего tick не могут
выглядеть как свежие текущие данные. Restart читает сохранённый снимок.
Старые accounts без нового поля совместимы; показано NOT_CAPTURED до обычной
обработки новой свечи. Миграция SQL или сброс состояния не нужны.

Использован существующий интерфейс load хранилища, как в owner status. Новый
endpoint не вызывает commit/control/advance. Существующий Supabase load RPC
может создать начальную запись, если account ещё отсутствует; в проверяемом
production account она уже существует. Для существующего account тесты
подтверждают неизменность revision, состояния и журнала при чтениях.

## Исторические примеры и причинность

Сохранена публичная история: `docs/data/AURA_TIMEFRAME_ALIGNMENT_BTCUSDT_15m.csv`.
5168 свечей 15m, 2026-08-23 02:00 — 2026-10-15 22:00 UTC (end exclusive).
SHA256: `2b9121b9ccf7d33d0b129713f902e5d0ca0846e96a1c4b7a6c18a6acaf3a95f5`.
Получена 2026-10-16 публичными GET того же Binance endpoint: production
`fetch_window` на cutoff 22:00 (4168 свечей) и предшествующая страница 1000 свечей.
CSV нормализован в поддерживаемые существующим импортёром шесть колонок.
Поле `source_claim` импортёра универсальное; фактическое приобретение описано здесь.
Это не исходный CSV прежнего 90-дневного исследования и не доказательство
неизменности upstream после production tick.

Проверены 64 cutoff с шагом 4h, последний отдельно 22:00; в каждом — точное
rolling production-окно. 43 MTF_NOT_ALIGNED, 20 NO_CONFIRMED_SETUP, 1 TREND_TOO_WEAK.
Найдено минимум три прохождения и три отказа:

| Close UTC | 15m | 1h | 4h | Alignment | Итог стратегии |
|---|---|---|---|---|---|
| 2026-10-05 12:00 | UP | UP | UP | PASS | NO_CONFIRMED_SETUP |
| 2026-10-06 00:00 | UP | UP | UP | PASS | NO_CONFIRMED_SETUP |
| 2026-10-06 12:00 | UP | UP | UP | PASS | NO_CONFIRMED_SETUP |
| 2026-10-05 16:00 | DOWN | UP | UP | FAIL | MTF_NOT_ALIGNED |
| 2026-10-05 20:00 | DOWN | UP | UP | FAIL | MTF_NOT_ALIGNED |
| 2026-10-06 04:00 | DOWN | UP | UP | FAIL | MTF_NOT_ALIGNED |

Полные значения: `AURA_TIMEFRAME_ALIGNMENT_EXAMPLES.json`.
Использованы существующие `PrefixCache`/`snapshot` из
`scripts/replay_auto42_verification.py` и сама production `strategy`.
Для шести примеров и последнего cutoff проверено точное равенство с native
анализом без cache и устойчивость к изменению доступных будущих OHLCV.
Для последнего cutoff будущих строк в CSV нет; независимый synthetic
prefix/future regression покрывает этот случай. Выбор старших TF всегда ≤cutoff;
пивоты доступны только после подтверждения. Новых виртуальных ордеров runner
не создаёт и `advance`/Service/storage не вызывает.

Отдельно `AURA_TIMEFRAME_ALIGNMENT_BASELINE.json`: на семи последних окнах
все исходные поля snapshot и strategy result совпали с неизменённым коммитом
0443867 после удаления только новых диагностических полей. Это проверка
поведения до/после, а не повторение одного изменённого вычисления.

## Совместимость пакета аналогов

Additive telemetry меняет hashes двух файлов, на которые строго привязан пакет
аналогов. Без обновления manifest он правильно отклоняется. Это обнаруженная
при тестировании регрессия новой диагностики, не причина октябрьского отказа.
Пакет перебинден с существующей строгостью checksums; обходов runtime validation нет.
Все 4136 исторических states, normalizers, outcomes, protocol и sample values
сохранены без изменения. Изменены только два software hash и content checksum.
Payload hash без software/checksum: `bea47e3768d366a456faed70ee039cc3a0e16407eacc5ea9ac923eb3f6e6e837`.
Новый gzip SHA256: `cb856cc3106ed48502a6f3963b4b8f26b314ad5b53b2645635de01e1c38a7a10`.
Одноразовый `scripts/rebind_alignment_metadata.py` принимает только известный
исходный artifact и ровно проверенные пары old/new hashes. Стратегия Auto42
по-прежнему не использует analog edge для разрешения входа.
Прежняя execution-verification панель может показывать прежнее доказательство
как outdated: изменились code hashes. Его нельзя выдавать за новый PASS.

## Проверки и review

Полный Python suite: **1186 passed**, одно upstream DeprecationWarning
Starlette/AnyIO. Все **15 Node suites PASS**, включая Paper, Bitget/BingX,
Bybit, Testnet, Auto42, Lab и новую alignment-панель. Python syntax всех файлов,
import app.main, `node --check static/alignment.js`, `git diff --check` — PASS.

Среда проверки: Python 3.12.14, Node 24.19.0, requirements.txt установлены в
временное venv: FastAPI 0.115.12, Uvicorn 0.34.2, HTTPX 0.28.1, pytest 8.3.5,
websockets 15.0.1, NumPy 2.2.6. Production requirements не изменялись.
Первый запуск без sandbox polling завис на TestClient; он остановлен, не засчитан.
Повтор использовал существующий diagnostic-only `enable_sandbox_poll` из
`scripts/replay_aura_csv.py` исключительно в test runner. Production loop не менялся.

Новые тесты: независимые EMA20/50, ADX14, ATR14, RSI14 reference values;
16 последовательных boundary cutoff; native/replay equality; future perturbation;
легитимные aligned/conflicting trends; inconsistent flag; отсутствующий h4;
stale data; reset warmup после gap; closed-window selection; missing legacy
snapshot; owner auth/no-store; повторные чтения без fetch/commit; restart;
duplicate/concurrent ticks и отсутствие неожиданных OPEN/CLOSE.
Существующие тесты дополнительно проверяют пропуски, freshness recovery,
позиционные лимиты, idempotency, restart, fees и защитные выходы.

Code review: прежнее тело strategy сохранено; additions не участвуют в risk,
направлении или порогах. Запись диагностики входит в прежний CAS commit;
duplicate не создаёт новый snapshot/event. Security review: owner dependency,
GET-only панель, no-store, textContent без HTML-инъекций; secrets/headers/URLs
с авторизацией в снимок не входят. Bitget/BingX модули не изменены.
Открытых high/critical findings в проверенном diff нет.
Реальный Supabase restart, Android browser и deployment — NOT RUN.
Автономный production open/close — **NOT_TESTED**.

## Воспроизведение и Render

```bash
python -m scripts.diagnose_timeframe_alignment \
  --csv docs/data/AURA_TIMEFRAME_ALIGNMENT_BTCUSDT_15m.csv \
  --output /tmp/alignment-examples.json --stride 16
git worktree add --detach /tmp/aura-baseline 04438674acf9a795a0666f8e1f2718221e7a9ed8
python -m scripts.verify_alignment_baseline \
  --csv docs/data/AURA_TIMEFRAME_ALIGNMENT_BTCUSDT_15m.csv \
  --baseline-root /tmp/aura-baseline --output /tmp/alignment-baseline.json
python -m pytest -q
node tests/test_alignment_frontend.cjs
```

Для этой cloud-среды вместо последней Python-команды:

```bash
python -B - <<'PY'
from scripts.replay_aura_csv import enable_sandbox_poll
enable_sandbox_poll()
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','--tb=short']))
PY
```

1. Проверить diff/PR и SHA коммита, который планируется развернуть. После
   одобрения интегрировать его в подключённую Render deployment branch.
2. Render → Manual Deploy → Deploy latest commit, либо дождаться существующего
   auto-deploy. Build/Start и Environment Variables оставить прежними.
   SQL не запускать, портфель не сбрасывать; scheduler configuration не менять.
3. Проверить `/api/health`. Войти существующим owner способом и открыть
   TIMEFRAME ALIGNMENT DIAGNOSTICS. До первого обычного нового решения допустим
   NOT_CAPTURED. Для заполнения не нужно вручную вызывать tick/START или сделки.
4. После обычного scheduler запуска проверить evaluated/processed close, EMA,
   направления, mask, exact reason, freshness, code identity/Render commit.
   Старое отклонение 15 октября не станет сохранённым production snapshot.
5. Если snapshot показывает INCONSISTENT_INPUTS, сохранить его JSON без
   credentials для отдельного разбора. Не обходить блокировку.

Развёртывание не выполнялось. Диагностический PASS не доказывает live autonomous
open/close execution и не разрешает реальные сделки.

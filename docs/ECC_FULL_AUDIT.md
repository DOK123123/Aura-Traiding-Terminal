# Полный ECC-аудит Aura Trading Terminal

Дата завершения: 14 октября 2026, Europe/Moscow.
Baseline: `68a33a32a214c11acb7279a91f5e3a428125b0dc`.
ECC: https://github.com/affaan-m/ECC, SHA
`b92f181b3b748d1abbc2afd94af6aa7d8c8fca29`.

**Вывод: READY_FOR_PAPER_ONLY_TESTING**, в пределах контролируемого ручного
виртуального тестирования. Это не разрешение реальной торговли, не подтверждение
profitability, не сертификат публичного 24/7 production deployment.

Найдено **11 подтверждённых дефектов**: 1 HIGH, 10 MEDIUM; CRITICAL не доказаны.
Исправлено **10**; публичный WebSocket admission риск оставлен документированным.
В intended diff нет незакрытых доказанных HIGH/CRITICAL. Severity главного агента
для credential leak — HIGH: тестом доказана возможность вывода key/secret,
хотя исходный специализированный reviewer первоначально оценивал её MEDIUM.
Настоящие credentials не использовались и их фактическая утечка не утверждается.

## Методика и scope

Сверены 229 baseline Git blobs; локального .git нет, diff восстановлен по
подлинным файлам GitHub. Прочитаны 30 pinned ECC source documents, установлена
одна instruction-only адаптация, сохранена MIT attribution.
[Совместимость/реальные роли](ECC_COMPATIBILITY_REPORT.md),
[точные результаты тестов](ECC_TEST_RESULTS.md),
[финальный независимый review](ecc/FINAL_INDEPENDENT_REVIEW.md).

Шесть независимых Codex reviewers проверяли architecture, security, trading
math, quant, frontend и QA; главный агент — Python/FastAPI и объединённый diff.
Новый независимый final reviewer подтвердил весь suite и обнаружил недочёт
MIME assertion, после исправления перепроверил его. Native Claude agents/plugin
не запускались. Проверены все first-party runtime/research module boundaries,
все JS/CSS/HTML, deployment entrypoint, tests и relevant reports/protocols.
131 Python files разобраны AST. Vendor chart engine проверен по версии,
лицензии, syntax и опасным sinks; полный семантический re-audit minified vendor
или каждой строки огромных trade-history JSON не заявляется.

## Подтверждённые findings

Ссылки/line numbers относятся к текущим функциям; воспроизведение выполнено
также на исходном baseline, а регрессии фиксируют исправленный контракт.

### ECC-01 — HIGH — поздние transport loggers обходили redaction

- Файл: `app/testnet/client.py:105`, handler coverage `:118`.
- Причина: filters только на существующих loggers; filters родительского logger
  не применяются к propagated child records, созданным позже.
- Доказательство: standalone dummy-only DEBUG/WARNING/traceback вывод содержал
  dummy key/secret; отдельный старый Testnet regression FAIL, общий suite мог
  скрывать проблему другими ранее настроенными filters.
- Impact: credentials/signed transport details могли попасть в server logs.
- Исправлено: filters на существующих output handlers и lastResort с cleanup,
  независимыми concurrent-reader guards. Host/allowlist/credentials не менялись.
- Тест: `tests/test_ecc_logging.py`, три cases. Поздняя произвольная
  переконфигурация logging handlers требует сохранения этих guards.

### ECC-02 — MEDIUM — отмена HTTP освобождала CPU слот раньше потока

- Файлы: `app/patterns/api.py`, `app/paper/signals.py`; общий fix
  `app/async_workers.py:8`.
- Доказательство: шесть отменённых вызывающих tasks оставляли одновременно
  шесть worker threads при лимите Pattern=2. Cancellation не останавливает to_thread.
- Impact: обход ограничений CPU/RAM; SignalReader имел ту же lifetime проблему.
- Исправлено: shield и удержание семафора до реального завершения worker,
  включая повторную cancellation и worker error. Формулы/cutoff не изменены.
- Тест: `test_ecc_architecture.py::test_repeated_cancellation_retains_real_worker_slot`,
  normal/error/queued cancellation. Это не жёсткое убийство долгого CPU процесса.

### ECC-03 — MEDIUM — неполные research source fingerprints

- Файлы: `scripts/pattern_research.py:25`,
  `scripts/run_pattern_research.py::compatible_protocol`,
  `research/market_intelligence/pipeline.py:20`.
- Доказательство: подмена `Path.read_bytes` только для `series.py`/`local_csv.py`
  не меняла checkpoint signature несмотря на изменение aggregation/import logic.
- Impact: устаревшие cached results могли выглядеть воспроизводимыми.
- Исправлено: реальные зависимости добавлены в manifests/kernel guard;
  diagnostic provenance также включает новый async helper.
- Тест: `test_changed_series_or_csv_dependency_invalidates_research_protocols`.
  Старые outputs не пересчитываются и не объявляются совместимыми молча.

### ECC-04 — MEDIUM — replay fingerprint не охватывал финансовые зависимости

- Файл: `app/intelligence/service.py:32`.
- Доказательство: изменение Lab models/indicators/strategies не меняло
  `software_sha256` существующей сессии.
- Impact: journal/portfolio мог пересчитываться новым кодом как прежняя сессия.
- Исправлено: hash closure расширен; несовместимая сессия возвращает
  `SOFTWARE_CHANGED`, persisted payload не удаляется и balances не переписываются.
- Тест: `test_changed_replay_dependency_rejects_existing_session_without_reset`.
  UI позволяет явно начать новую сессию после authenticated metadata reload;
  это не автоматическое исполнение или удаление старой истории.

### ECC-05 — MEDIUM — bootstrap сжимал календарь и терял известные flat days

- Файл: `scripts/pattern_research.py:107`, producer `:149`; общий bootstrap MI3.
- Доказательство: одна и та же известная equity trajectory (100 cash-only days,
  затем 60 daily increments) давала days=60 вместо160 при sparse endpoint output.
  Nonadjacent days выбрасывались и оставшаяся последовательность трактовалась
  как непрерывные 14-calendar-day blocks.
- Impact: искажённая uncertainty, среднее/day и selection evidence.
- Исправлено: incomplete calendar → undefined inference/INCOMPLETE_CALENDAR;
  cash-only continuous segments сохраняют реальные observed UTC markers.
  Нет заполнения отсутствующих свечей/неизвестного капитала через gaps.
- Тест: шесть `tests/test_ecc_quant.py`; dense seed arithmetic сохраняется.
  Старые bootstrap numbers нельзя считать перепроверенными этим fix; grid
  не повторялся, original reports не менялись, положительное edge не заявляется.

### ECC-06 — MEDIUM — новый tight stop мог исполняться по недоступной цене

- Файл: `app/lab/execution.py:102`, вызов после нового entry `:115`.
- Доказательство: raw open100, entry slippage5bps, LONG stop distance0.04:
  stop выше raw open. Старый engine использовал поздний intrabar stop price
  вместо немедленного adverse raw-open exit. LONG/SHORT и фиксированный Donchian
  воспроизводят случай; это алгоритмический fixture, не profitability test.
- Impact: оптимистичный PnL при достаточно узких защитных уровнях.
- Исправлено: protective opening check сразу после entry, raw-open adverse fill,
  до последующих high/low. Priority existing gaps/strategy exit сохранён.
- Тест: Fraction oracle, LONG/SHORT/gap/ambiguous/fee-inclusive sizing в
  `tests/test_ecc_trading_safety.py`. Strategy/stop-distance параметры не менялись.

### ECC-07 — MEDIUM — OHLC correction с тем же close оставляла FRESH

- Файл: `app/paper/engine.py:37`, observation `:490`, advance `:501`.
- Доказательство: processed high105 → corrected111 при close100 и TP110
  оставляло позицию OPEN/FRESH, без ошибки исправленной истории.
- Impact: отсутствующее исполнение и неверная видимость доверия к истории.
- Исправлено: точный OHLC fingerprint, отдельно known volume, durable correction
  latch, безопасный preflight safety observation перед потенциально отклонённым
  manual command. Нет ретроспективного выдуманного TP/SL или balance rewrite.
  Unknown volume → known не считается противоречием; known→unequal known — correction.
- Тест: LONG/SHORT, rejected open/close/no fees, source/timeframe scope,
  restart/corruption/idempotency и legacy metadata в `test_ecc_trading_safety.py`.
- Важное ограничение: proven correction остаётся paused/unknown до отдельно
  проверенной reconciliation policy. Новый recovery/write endpoint не добавлен.
  Legacy records без OHLC fingerprint не способны доказать более ранние revisions.

### ECC-08 — MEDIUM — Replay action после ошибки использовал null state

- Файл: `static/intelligence.js:13` и action/Load handlers.
- Доказательство: после failed Advance current=null, sid остаётся; старый
  Propose активен, читает current.analysis и падает в пустой catch. Create до
  manifest тоже не давал понятной ошибки.
- Исправлено: authoritative session gating и видимые ошибки; verified metadata
  не объявляется готовой после partial failure. Отдельная безопасная обработка
  immutable SOFTWARE_CHANGED/DATASET_CHANGED/NOT_FOUND после явного Load.
- Тест: stateful VM cases `tests/test_ecc_replay_frontend.cjs`.

### ECC-09 — MEDIUM — Replay request мог навсегда удерживать pending controls

- Файл: `static/intelligence.js:19`.
- Доказательство: fetch/body обещание не завершалось; таймера abort не было.
- Исправлено: 35s timeout, finally cleanup; uncertain POST outcome сбрасывает
  cached confirmation state и требует явного authenticated GET reload.
  Никакого automatic retry mutation, предложения или подтверждения.
- Тест: read/write/body timeout, no retry, reload/recovery, native confirm,
  old incompatible session — тот же stateful Node suite, 11 PASS.

### ECC-10 — MEDIUM — owner action document разрешал framing

- Файл: `app/main.py:76`, ProtectedStaticFiles `:83`.
- Доказательство: root и `/static/index.html` возвращали тот же interactive UI
  без X-Frame-Options/CSP. Initial fix только root не закрывал static URL;
  независимый reviewer воспроизвёл обход, он исправлен до commit.
- Impact: clickjacking ручных виртуальных actions/settings; не заявляется обход
  отдельного native confirm для Intelligence/Auto enabling.
- Исправлено: DENY/frame-ancestors none/nosniff на actual HTML response,
  включая normalized static paths. Script MIME behavior не менялся.
- Тест: root/static/double slash/trailing slash, плюс22 independent GET/HEAD probes.

### ECC-11 — MEDIUM — публичный WebSocket не имеет admission cap

- Файл: `app/live.py:163`, `serve_market`.
- Доказательство: offline24 sockets без owner/auth и с cross-origin metadata
  принимаются и создают24 независимых producer tasks. Реальная нагрузка на
  Binance/Render или production outage не выполнялась и не измерялась.
- Impact: возможное усиление upstream/CPU нагрузки публичного quote endpoint.
- **Не исправлено:** public market read не равен приватному action; скрытая
  новая auth/quota policy могла бы изменить существующий терминал. Для публичного
  production нужен отдельный согласованный admission/shared-feed design,
  deterministic cap/cancel tests и измерение реальной нагрузки.

## Проверенные safety boundaries

- Engine/store не имеют private exchange execution clients. Testnet и Demo
  сохраняют официальные hosts, GET allowlists и owner protection. Никаких
  create/amend/cancel/transfer/withdraw реализаций не добавлено.
- Owner auth и CSRF server-side; без explicit confirm Intelligence Replay не
  исполняет предложение. Auto Paper сохраняет прежний отдельный owner opt-in,
  default OFF/generation protection: этот аудит его не включал и не менял.
  Не утверждается, что уже разрешённый владельцем Auto требует клика на каждый
  виртуальный trade; individual confirmation относится к Intelligence Replay.
- CLOSED-only causal prefixes, confirmed pivots с отдельным confirmation time,
  complete UTC MTF blocks, purged/resolved past analogs и gap resets проверены.
- Decimal/Fraction LONG/SHORT costs, risk/notional, equity, restart, duplicate IDs,
  cancel-and-retry и OFF acknowledgement покрыты. Risk budget — планируемый
  риск, не гарантия цены исполнения через неизвестный market gap.
- Historical unknown/censored outcomes не выдаются за wins. Conditional gap-ledger
  и archive quarantine ограничения сохранены; synthetic fixtures только unit tests.

## Market Intelligence 1.0 / 2.0 / 3.0 / 3.1

Adaptive1.0 Replay остаётся отдельным виртуальным портфелем с owner confirmation.
21 реализованный и9 experimental detectors используют existing registry;
43 PLANNED не выдаются за алгоритмы. Analog scores/CI descriptive,
не probability гарантия и не независимые коррелированные votes.

Pattern2.0/Market3.0: confirmed pivots, HH/HL/LH/LL, BOS/CHoCH, sweep,
SR zones, breakout/retest, past-only normalization, outcome cutoff/purging,
MTF/gaps и frozen parameter boundaries просмотрены. Подтверждённого
look-ahead дефекта в проверенных путях не найдено; это не математическое
доказательство отсутствия любого будущего бага. Шестилетний archive
первоначально независимо проверен:210280 raw,152 missing,8 quarantined,
210272 valid,160 effective missing,27 annotations. Разные виды counts
не складываются как повторные потерянные свечи.

MI3.1 runtime adapter не загружает archive/runner и не мутирует portfolios.
4175 maximum15m bars, отдельный250-bar warmup, stale/UNKNOWN/null и
ANALOG_DATA_UNAVAILABLE честно показаны. Пакет1.0 не выдаётся за признаки3.0.
42 конфигурации/0 candidates — ссылка на завершённое исследование, **не live
expectancy**. Decision всегда WAIT/READ_ONLY/FORWARD_VALIDATION_REQUIRED.
2025 уже просмотрен, не новый blind holdout. Нет forward-validated profitability.

### Различия моделей исполнения и статистики

Live Paper/Auto сохраняют прежний `VERIFIED_CLOSED_CANDLE` fill model:
entry по проверенному последнему close и комиссии из Paper Settings.
Отдельной slippage настройки/модели в этом Paper engine нет; backend/UI
честно показывают unsupported. Lab и Intelligence Replay используют
next-open/adverse slippage. Их результаты нельзя считать тождественными
live Paper или реальному исполнению. В этом аудите slippage в Paper не
добавлялось: это новая модель, требующая отдельного протокола/тестов.

В Market3.0 ранее отмечены отсутствие warmed4h calibration observations
в2020Q1 и сильный clipping h4 признака после calibration. Эти limitations
не исправлялись подбором параметров и не выдаются за доказательство
алгоритмической ошибки или edge. Совместимый live analog pack не установлен.

## Остаточные риски и следующий шаг

1. MEDIUM ECC-11 admission риск; HTTP auth throttling и public redirect policy
   требуют отдельной hardening оценки. Не заявляется доказанный SSRF/account compromise.
2. Полный dependency advisory scan, coverage/types/lint и real browser/Android
   ещё не выполнены. Transitively разрешённые версии не полностью locked.
3. CPU slots теперь реальны, но uncancellable Python worker не убивается жёстко;
   крупный накопленный Pattern archive и Render Free load требуют измерения.
4. Render filesystem ephemeral: постоянство SQLite между заменой инстанса не гарантируется.
   Реальные backup/restore/expiry меры не проверены этим локальным тестом.
5. Старые replay sessions/checkpoints сохраняются, но новые hashes отказывают
   их пересчёт другим кодом. Для воспроизведения нужен original software build;
   UI может явно создать новую session, не удаляя прежние данные.
6. Корректированная Paper история требует отдельно спроектированной owner-reviewed
   reconciliation; нельзя молча снять pause или придумать пропущенный exit.

**Render: NOT_DEPLOYED / configuration unchanged. Android: NOT RUN.**
После ручного/обычного проверенного обновления откройте существующий Render URL
с `/#market-analysis`; точный домен в репозитории не указан. Проверьте owner login,
15m/1h/4h freshness/UNKNOWN, offline/timeouts, WAIT, layout320–430px,
replay confirm/decline/next-open, explicit recovery после timeout/SOFTWARE_CHANGED,
manual Paper, saved Auto OFF и stop protection. Никаких новых алгоритмов не
включать в execution. Для подтверждения edge нужен новый preregistered forward
paper период; текущий аудит не делает стратегии прибыльными.

## Точный список файлов delivery

14 существующих файлов изменены,15 новых добавлены; ничего не удалено.
Зависимости/архивы/SQLite/временные логи не входят в commit.

- `.agents/skills/ecc-full-audit/SKILL.md`
- `app/async_workers.py`
- `app/intelligence/service.py`
- `app/lab/execution.py`
- `app/main.py`
- `app/paper/engine.py`
- `app/paper/signals.py`
- `app/patterns/api.py`
- `app/testnet/client.py`
- `docs/ECC_COMPATIBILITY_REPORT.md`
- `docs/ECC_FULL_AUDIT.md`
- `docs/ECC_TEST_RESULTS.md`
- `docs/ecc/AUDIT_TEST_EVIDENCE.json`
- `docs/ecc/AUDIT_UPSTREAM_MANIFEST.json`
- `docs/ecc/FINAL_INDEPENDENT_REVIEW.md`
- `docs/ecc/UPSTREAM.md`
- `research/market_intelligence/pipeline.py`
- `scripts/diagnose_aura_auto.py`
- `scripts/pattern_research.py`
- `scripts/run_pattern_research.py`
- `static/intelligence.js`
- `tests/test_ecc_architecture.py`
- `tests/test_ecc_logging.py`
- `tests/test_ecc_quant.py`
- `tests/test_ecc_replay_frontend.cjs`
- `tests/test_ecc_security_headers.py`
- `tests/test_ecc_service_safety.py`
- `tests/test_ecc_trading_safety.py`
- `tests/test_paper_engine.py`

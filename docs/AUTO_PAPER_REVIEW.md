# Auto Paper implementation review / evidence

Baseline main: `b3b903feed1eac9b6932d4226913344c2b66cbb8`.
User scope authorizes **only virtual Auto Paper**, default OFF, explicit UI ON,
existing confirmed signals, no real orders or Bybit regional bypass. Nine separate
ECC/Aura review passes were performed by the current executor; no independent
agents were launched or claimed. Existing strategy formulas/defaults unchanged.

## Review passes

| Pass | Evidence / outcome |
|---|---|
| Architecture | Public callbacks -> server SignalReader -> network-free Auto coordinator -> existing Decimal ledger. No private account or execution client dependency; mode API cannot accept signals/credentials/hosts. Bybit/Binance kept separate. |
| Python/FastAPI | Atomic SQLite decision/trade/command/watermark, savepoint rejection rollback, generation race checks, service locks, coroutine cancellation, bounded reads, strict owner/CSRF DTOs, safe failures. Legacy manual journal/curve migration and backup restore tested. |
| Frontend | Explicit ON/OFF/resume, explicit fallback, mode/source/scope/rejection display, virtual-only label, independent MANUAL/AUTO views, stale/hidden/bfcache behavior retained. Late-filter race fixed; owner/error/XSS-safe rendering tests pass. |
| Security | Entire paper package has no HTTP/private exchange imports or exchange writers. All app HTTP writes are only same-origin FastAPI routes, not exchange calls. No credential literals or key/secret/host overrides. No proxy/VPN/403 bypass added. |
| Trading math | Existing money/risk formula reference tests remain; auto LONG/SHORT fees/PnL/balance independently compared with Fraction/integer-tick oracle; precision 64, quantity flooring, risk <=1%, one open position, and attribution DD checked. |
| Look-ahead | Cutoff precedes feature/match/MTF/outcome calculation. Tests perturb future/forming bars and obtain identical real pattern signal; adapter compares source and closed market tail OHLCV. No backfill entry; activation/resume baseline skips current historical close. |
| Paper Trading | No replacement strategy/engine. Shared opening logic operates inside coordinator transaction, tags metadata, retains fees/stops and old closed-bar exit semantics. Existing manual tests and backup/restart pass. Generic arbitrary-signal handle remains disabled. |
| Reliability | ON restores PAUSED; transient data pause / manual error recovery distinct. Duplicate REST/reconnect/concurrency/closed position/rotated log never reopen same candle. Mode changes during async computation and obsolete errors are rejected. Ephemeral disk limitations explicit. |
| Testing | Offline tests cover required paths, strict API security and UI states. Full original 483 tests retained with intentional manual fixture max=3 explicit and endpoint allowlist expanded only for local `/api/paper/auto`. No mocked exchange orders or live credentials. |

## Confirmed implementation findings fixed before commit

- **HIGH — potential duplicate/partial commit:** separate decisions and ledger
  commits would allow retry/restart duplicate fees or entries. Coordinator now
  owns one BEGIN IMMEDIATE transaction and calls the shared engine opening logic
  in it. Deterministic command/signal ID + permanent per-TF watermark; concurrent,
  transaction-failure, restart, reconnect, post-close and rotation tests prove
  one candle cannot open twice while persistence remains intact.
- **HIGH — execution after OFF / old scope:** delayed signal or delayed failure
  could affect a newer configuration. Persisted generation is rechecked inside
  transaction; stale computation does not enter, stale failure cannot pause the
  newly armed scope. Regression covers both.
- **HIGH — future-bar influence:** a fetched archive can contain later candles
  than the market reference. They are clipped before evaluate/feature/MTF work;
  full causal engine tests with extreme future/forming candles produce the same
  result. Exact tail identity also rejects wrong source/timeframe/price/volume.
- **MEDIUM — manual/auto portfolio cap:** a legacy manual setting of three positions
  could open a manual second position while Auto is armed. Core now caps *all*
  new positions at one in armed mode; previous positions are not forcibly closed.
- **MEDIUM — filtered-statistics race / misleading state:** late ALL response
  could repaint AUTO and filtered empty results could unlock starting balance in
  UI. Generation-aware queued refresh and server-global starting-balance lock
  flag fix these without changing accounting. Node regressions pass.
- **MEDIUM — statistics name collision:** new DD value reused the old losing-streak
  variable name. Existing streak reference test caught it; renamed and fixed.
- **MEDIUM — missing/corrupt attribution:** rebuilding missing auto history would
  fabricate past results. Legacy-only migration allowed; tagged-auto missing
  slices fail closed. Slice money, peaks/DD and balance/equity decomposition
  checked at restart; corruption regression passes.

No unresolved critical/high finding identified in this scoped offline review.
This is not a formal proof of profit, exchange realism or absence of every defect.

## Final validation

- **536 Python tests PASS**, including all 483 baseline cases and 53 additional
  Auto/API cases. All existing independent trading-math and market/reliability/
  account read-only regression suites pass.
- **60 Node tests PASS**: 9 market, 11 Binance, 13 Bybit, 27 Paper/UI (8 new).
- **53 Python source files** parsed; all app modules imported. All local static
  JavaScript and Node test files pass `node --check`.
- Heuristic static credential scan / no .env files, entire-app exchange write-
  method/endpoint scan, paper dependency boundary, HTML asset/ID references and
  responsive CSS structural checks PASS. Scans report locations only on failure,
  never matched credential text. No actual keys added, printed or requested.
- Test dependencies were absent in the replaced Cloud environment. One pip
  attempt was interrupted; it was **not repeated**. Official pinned pytest 8.3.5,
  pluggy 1.5.0 and iniconfig 2.0.0 source files were fetched through the GitHub
  connector into `/tmp/aura-test-deps` only. Generated version metadata matches
  those tags; no test-tool dependency/source entered the repository. Existing
  packaging/pygments were used. Pytest plugins/cache disabled; temporary event-loop
  wakeup accommodation remained outside production. One existing Starlette warning.
- Runtime used: FastAPI 0.141.1, Uvicorn 0.52.1, HTTPX 0.28.1, websockets 16.0,
  NumPy 2.3.5. Requirements pins unchanged; exact pinned Render environment **NOT
  RUN** here. No new application dependency.
- **Live Render / actual Android/mobile browser NOT RUN**. CSS/DOM tests do not
  prove screenshots, touch behavior or live account connectivity. No server/port/
  preview, live private exchange requests or external deployment was performed.

## Remaining limitations / manual acceptance

Auto is BTCUSDT only, uses unchanged v1 default historical research settings and
context 500. Existing EMA/RSI score is not treated as a new execution strategy.
Confidence is uncalibrated; valid directional signals may be rare. Current strategy
has no stops: default SKIP makes no entries until explicit PAPER_SETTINGS policy.

Fills are closed-price simulations with existing conservative OHLC exit rules,
not instant bid/ask. Archive/cache tail mismatch or slow computation can skip a
candle; rejection is visible, not silently executed later. Missed entry candles
never backfill. Multi-TF/historical equity gaps are not guessed. Attributed AUTO/
MANUAL curves share a starting baseline, not spendable separate accounts.

Render Free sleep pauses processing. Same DB restart preserves watermarks but
requires resume; lost ephemeral DB starts OFF and cannot preserve old journal or
lifetime dedup. Old backup only restores knowledge up to backup time. No paid
storage added. Download backup before migration/restart tests. Audit log bounded
2000 / 30 days; existing trade/equity journal remains complete and can grow.

Manual checklist: see `AUTO_PAPER_TRADING.md` for explicit ON/policy/scope, next
closed candle, WAIT/rejection log, one-position cap, journal/stops, statistics
filters, OFF/resume and Render backup/recovery. Bybit HTTP 403 may remain visible;
it must neither block Auto nor trigger a bypass.

## File inventory

Created: `app/paper/auto.py`, `app/paper/signals.py`, `tests/test_auto_paper.py`,
`docs/AUTO_PAPER_TRADING.md`, `docs/AUTO_PAPER_REVIEW.md`.

Modified: `app/main.py`; `app/paper/{models,market,storage,engine,service,api}.py`;
`static/index.html`, `static/paper.js`; `tests/test_paper_engine.py` (manual fixture),
`tests/test_paper_api.py`, `tests/test_paper_frontend.cjs`; `README.md`, `AGENTS.md`,
`docs/PAPER_TRADING.md`, `docs/ecc/TRADING_REVIEW.md`.

No strategy/indicator/matching/backtest/market provider or chart script changed.
Bybit/Binance account code, credentials, runtime dependencies and ECC attribution/
license notices unchanged. New read-only GET market/history callbacks reuse the
existing public pipeline. Only local paper mode control endpoint added.

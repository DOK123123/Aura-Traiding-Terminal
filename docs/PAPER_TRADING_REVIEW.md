# Paper Trading implementation review

Review uses explicit ECC/Aura perspectives, not separately launched agents:
architecture/planning, Python/FastAPI, code, security, testing and hidden-error
passes. No exchange account or Render credentials were accessed. Main baseline:
`6776d5c7b6013cf03290123f0530267a55d2a1e8`.

## Architecture and scope

Market/analysis/pattern/backtest files and account clients are unchanged, verified
against baseline Git blob hashes. `app/main.py` adds only paper router/lifespan
wiring and an injected callback to the existing validated closed-market reader.
No runtime dependency was added. SQLite/Decimal core has no network/client or
exchange imports. Local POST ledger actions are owner/CSRF protected and cannot
reach private exchange endpoints. Automatic signal entry is hard-disabled.

Manual closed-price fills, 1× collateral for both sides, conservative stop/target
bar ordering and paper-specific commissions are documented, without claiming
exchange realism or calibrated strategy profitability. Settings do not offer
real-money, account-provider or automatic-execution overrides.

## Confirmed findings and fixes

| Severity | Location | Evidence / impact | Fix and verification |
|---|---|---|---|
| High | `engine.open`, request journal / frontend pending actions | A retry after timeout or reload could otherwise open/charge twice. | Unique persisted command ID + payload hash atomically coupled to trade; same-ID replay precedes market fetch. sessionStorage preserves pending command across reload with explicit retry only. Concurrent/restart/offline replay and conflict tests pass. |
| High | `engine._advance` | First bar overlaps manual entry; earlier high/low can invent a pre-entry SL/TP. | Overlapping bar uses close only; subsequent full bars use OHLC. Regression verifies pre-entry ranges do not close the position. |
| High | startup ledger validation | Missing version or corrupted fees/balance might silently seed/reset a virtual account. | Nonempty journal without version fails closed; validate fee, closed PnL and balance invariants. Corrupt journal disables paper and does not reset it; market health still starts. |
| Medium | `static/paper.js` market listeners | Existing market events are dispatched on `document`, not `window`. | Listen on document; invalidate stale/source-mismatched quote and verify selected symbol/timeframe against current chart data. Offline UI tests pass. |
| Medium | `storage.connect`, `backup` | SQLite connection may leak on PRAGMA/backup paths. | Explicit close on initialization failure and finally-close memory backup connection. Consistent backup restores into a separate valid ledger. |
| Medium | `engine._point`, statistics | Truncated curve could erase historical drawdown; undefined PF/win rate could become misleading zero/infinity. | Persist peak/max drawdown separately; return null for missing denominators/evidence. Reference drawdown, stats, truncation tests pass. |
| Medium | `api.py` local mutations | HTTP Basic alone does not establish CSRF safety. | Require custom local-only header, reject cross-site fetch metadata and foreign Origin, forbid extra DTO fields, protect all paper reads even with no exchange keys. Auth/CSRF/strict-model tests pass. |
| Medium | stale/corrected/gapped marks | Old/source-mixed or missing bars could produce invented equity/stops. | Reject malformed/future/gapped input; freeze affected marks/protective exits on mismatch/gap/correction. Equity unknown -> null; fee-inclusive new risk checks block. Explicit manual gap close preserves warning. Tests pass. |

Review corrected test assumptions rather than weakening guarantees: modern
FastAPI exposes lazy included routers, so route-write audit uses OpenAPI paths;
existing pattern-analysis/backtest POSTs are not exchange-order endpoints. A
fresh matching window intentionally restores the same position's stale mark;
the stale-equity new-entry regression uses another timeframe that cannot refresh
that mark.

No unresolved critical/high finding identified in the reviewed scope. This is
source/offline test evidence, not proof of live service uptime or trading returns.

## Validation evidence

- **437 Python tests PASS**, including 91 new paper tests and existing 346.
  Ordinary command: `python -m pytest -q`. In this Cloud session pytest 8.3.5 was
  available only through existing temporary `/tmp/aura-test-deps`; no package
  installation was performed. Launcher disabled external pytest plugins/cache
  and used a temporary event-loop wakeup accommodation for sandbox TestClient
  waits. No production event-loop patch was added. One existing Starlette
  TestClient/httpx deprecation warning.
- **50 Node tests PASS**: 9 market, 11 Binance Testnet, 13 Bybit Demo, 17 paper;
  all four `node tests/test_*frontend*.cjs` suites listed in AGENTS.md were run.
- **49 Python files parsed**; `app.main` and all six paper runtime modules import.
  `node --check static/paper.js` passes.
- Static secret patterns (private keys, GitHub/AWS tokens, credential literals)
  scanned all text sources; real credentials / `.env` files not found. Scan
  reports only locations/categories if a match occurs, never credential text.
  This is a heuristic static scan, not a claim of a formal exhaustive proof.
- AST import/constant audit: paper package contains no private exchange clients,
  HTTP client imports, production account hosts or order-writing endpoint strings.
  API write-route audit limits paper writes to local settings/refresh/open/close.
  Existing read-only account tests pass and their source blob hashes are unchanged.
- HTML asset links, unique IDs, paper JS DOM references, SVG/status accessibility,
  mobile CSS breakpoint/grid/min-width, internal table scrolling, 44px action
  targets and 16px input text checked. Offline DOM UI tests cover owner states,
  stale/source/timeframe changes, wrong safety identity, pending recovery, XSS-safe
  text rendering and equity gaps.
- **Real mobile browser layout NOT RUN successfully**: installed Chromium failed
  to launch because Cloud disallows a required socket operation (`setsockopt`,
  SIGTRAP). No sandbox relaxation, external browser service or network preview
  was used. Actual 320/390px phone rendering/touch and live Render behavior still
  need user verification after deployment; structural tests are not screenshots.
- Tested installed runtime: FastAPI 0.141.1, Uvicorn 0.52.1, HTTPX 0.28.1,
  websockets 16.0, NumPy 2.3.5. Requirements pins remain unchanged (FastAPI 0.115.12,
  Uvicorn 0.34.2, websockets 15.0.1, NumPy 2.2.6); exact pinned runtime test was
  **NOT RUN**, no network dependency installation attempted.

## Remaining operational/model limitations

- Render ephemeral disk can lose the DB at redeploy/restart. Consistent owner-only
  download backup exists; reliable long-lived history needs a user-provisioned
  persistent path/disk. No paid service was provisioned. Free sleeping service
  cannot run protective exits continuously.
- Polling/closed-candle fills are not exchange ticks. First partial-bar ranges,
  intrabar timing, spread, leverage, funding, borrowing and ordinary execution
  slippage are not modeled. SL cannot guarantee risk budget through a gap.
- Historical protective replay is bounded to available contiguous 500 bars;
  gap/source error pauses virtual processing, does not invent missing outcomes.
- One-worker SQLite deployment; snapshots read full trade history for statistics.
  Large/distributed workloads would need separately scoped storage/aggregation.
- No automatic strategy paper entry, no XAU USD/USDT conversion, no real-money
  execution. Existing Binance/Bybit account reads remain independent.

## File inventory

Created:
- `app/paper/__init__.py`, `models.py`, `storage.py`, `engine.py`, `market.py`,
  `service.py`, `api.py`.
- `static/paper.js`, `static/paper.css`.
- `tests/conftest.py`, `tests/test_paper_engine.py`, `tests/test_paper_api.py`,
  `tests/test_paper_frontend.cjs`.
- `docs/PAPER_TRADING.md`, `docs/PAPER_TRADING_REVIEW.md`.

Modified:
- `app/main.py`: router/lifespan and injected public-market callback only.
- `static/index.html`: paper panel and its local CSS/script references.
- `.gitignore`: exclude virtual DB, WAL/SHM and backups.
- `README.md`, `AGENTS.md`, `docs/ecc/TRADING_REVIEW.md`: setup, safety and review
  guidance. ECC attribution/license files remain untouched.

Total: 15 new + 6 modified files. No existing account integration, market,
indicator, strategy, chart JavaScript, backtest or requirements file changed.

# Bitget-only active terminal

The main BTCUSDT chart and Historical Analogs now read Bitget V2 USDT-M Futures,
with the same source identity as Aura 4.3. OHLCV base volume is BTC, pagination
uses exact exclusive candle boundaries, only closed bars enter analytics, and
invalid/gapped/stale data fail closed. No fallback exchange is called.

The chart checks Bitget server time every five seconds and appends completed
candles at the interval boundary. This initial migration does not provide a
forming candle or tick-level main-chart price. The separate Aura 4.3 panel keeps
its existing fresh last/mark quote display and its unchanged PAPER engine.

Bybit Demo, Bybit preview, Binance Testnet/Spot, legacy Paper/Auto42, Practice,
legacy Intelligence and Strategy Lab are retired from the active UI. Their
source code and stored data are preserved; HTTP routes return 410 before any
upstream or ledger operation. Legacy monitors do not start. XAUUSD is rejected
rather than substituted with a different exchange instrument.

## Release gate

Do not deploy this migration until the owner verifies legacy Paper, Auto42 and
Practice are OFF, with no open positions or pending operations. Retiring a
monitor with an existing position would also retire its protective virtual exits.
Do not automatically close, migrate, reset, or reprice any legacy account.

Do not change any saved Active43 mode, strategy, thresholds or risk settings.
PAPER is never enabled by this change. Existing owner authentication remains.
After CI/review, deploy the exact approved commit, verify 500/2000 bars for each
1m/5m/15m/1h interval, source identity, a new candle boundary, error recovery,
no requests to retired providers, and read-only Active43 balance/journal status.
A passing unit test does not prove production Bitget connectivity.

## Review

Code: checked source identity, UTC/closed-bar validation, bounded pagination,
cancellation, exact base volume, cache separation and fail-closed retired routes.
Security: fixed public Bitget host/GET endpoints, redirects disabled, no account
keys, owner auth unchanged, no exchange writers or stored mode changes.
Residual release blockers: legacy-position snapshot, live Bitget chart checks from Render and the owner confirmation that all retired
ledgers are OFF and flat. This is a draft migration until
those checks are complete.

## Validation in this workspace

- Full offline Python suite: 1785 passed, 3 skipped (before the final two added
  boundary tests). Final targeted chart/history run: 28 passed.
- All JavaScript regression suites: 251 passed.
- Python syntax/import, changed JavaScript syntax and diff whitespace checked.
- Preserved legacy API/UI tests run against a test-only router harness and frozen
  HTML fixture. Actual production retirement, no legacy constructors, method
  rejection, source separation and Bitget validation have separate new tests.
- Test runtime: Python 3.12; runtime requirements installed as pinned. Transitive
  versions include Starlette 0.46.2 / Pydantic 2.14.1; CI uses its own lockfile.
- Proxy environment was removed only for offline mock tests; no production
  proxy, application networking, credentials or provider configuration changed.
- No live chart request, trading operation, migration or production deploy run.

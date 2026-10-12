# Aura market, signal and trading-safety review

Aura-specific guidance, complementary to ECC. This checklist adds no runtime
controls or execution feature. Read AGENTS.md and RULES.md first.

## Ingestion and freshness

Review `app/models.py`, `providers.py`, `gold.py`, `market_state.py`, `live.py`,
`main.py`, `patterns/api.py` and `static/live.js`, `static/patterns.js`.

- OHLCV is validated, UTC/aligned, ordered and deduplicated. NaN/Infinity,
  impossible ranges, future timestamps and invalid volume are rejected.
- Binance REST pagination/count and closed-candle handling match the requested
  interval; WebSocket events use the correct symbol/interval and timestamp units.
- Late/duplicate events cannot roll back the candle. Gaps or missing final events
  require a fresh coherent snapshot. Retries/backoff are bounded and cancellable.
- Source identity follows the entire window/analysis. Fallback never silently
  mixes gold providers or replaces exchange data with mock prices.
- Cached/streaming/provisional/closed/stale states remain honest. Disconnection,
  stale delivery and source mismatch suppress actionable freshness in the UI.
  Any future execution gate must independently reject stale data server-side.

## Indicators and signals

Review `app/indicators.py` and `app/patterns/{features,matching,outcomes,engine,
signals,backtesting}.py` with their tests.

- Compare EMA/RSI/ATR seeding, warm-up and recurrence with independently verified
  fixtures; check flat series, insufficient history, zero ranges and precision.
- Do not change weights, thresholds, horizons or formulas without a justified,
  explicitly scoped change and before/after reference evidence.
- No future candles or outcomes enter the decision at the historical cutoff.
  Preserve causal features, admissible historical analogs and non-overlap rules.
- Signal score/confidence is not a calibrated profit probability. Missing volume
  or higher-timeframe evidence cannot become invented confirmation.
- Backtest entry/exit timing, LONG/SHORT signs, bps conversion, costs, WAIT
  treatment, compounding and drawdown match documented semantics. Report absent
  spread/slippage modeling and sampling/truncation limits honestly.

## Read-only Testnet and credentials

Review `app/testnet/{client,api}.py`, `static/testnet.js`, `tests/test_testnet.py`
and `tests/test_testnet_frontend.cjs`.
Also review `app/bybit_demo/{client,api}.py`, `static/bybit_demo.js`,
`tests/test_bybit_demo.py` and `tests/test_bybit_demo_frontend.cjs`.

- Only the fixed official Demo/Testnet APIs and allowed GET endpoints are used. No
  production account fallback, order-writing methods, transfers or exchange keys
  in market ingestion. Public production quotes do not authorize real trading.
- HMAC key/secret stay server-side in environment variables; signed URLs, headers,
  exceptions and upstream bodies cannot disclose them. Redirects stay disabled.
- Configured account reads require owner access; absent keys mean Not configured
  with working market UI. Cache is bounded in freshness and failures hide old data.
- Timeout, invalid keys/data, clock errors, cooldown and temporary network loss
  have offline regression coverage. Test data is clearly dummy, never actual keys.
- Bybit is pinned to `api-demo.bybit.com`, V5 HMAC GET signatures and Demo-only
  keys. No funding/top-up, transfer, withdraw or order-writing endpoints. Preserve
  explicit VIRTUAL FUNDS / REAL MONEY IS NOT USED and provider/scope identity.
- UNIFIED wallet balance, equity, spot-locked assets and available margin are
  different quantities. Do not invent per-coin free funds from deprecated fields
  or mislabel USD totals as USDT. Paginated reads must have bounded time/counts
  and explicit truncation/scope; do not present partial history as a complete log.

## Mandatory gate for future execution changes

Do not implement execution as part of installing ECC or reviewing this checklist.
If a separate future task authorizes demo/paper execution, its integration requires:

1. A scoped plan, explicit environment identity and read/write authority; no
   automatic real-money mode and no production credential/source fallback.
2. Passing offline tests for quantity/price/notional limits, Decimal rounding,
   insufficient funds, stale/source-mismatched data, duplicate/idempotent execution,
   timeout with unknown outcome, loss/exposure limits and restart behavior.
3. Independent risk validation outside signal/LLM output, defined emergency stop,
   position/account reconciliation, fees and SL/TP semantics where applicable.
4. Explicit code review and security review with findings, evidence and outcomes.
   Failed checks and unresolved critical/high findings block integration.
5. A user-authorized integration/release step. Test success or a commit is not
   authorization to place an order. Automated tests never submit exchange orders.

Real-money trading remains prohibited by default. An eventual production feature
needs a separately authorized opt-in that defaults disabled and cannot be enabled
merely by setting keys. None of those future features is introduced here.

## Paper Trading review

Review `app/paper/`, `static/paper.js`, `tests/test_paper_*.py` and
`tests/test_paper_frontend.cjs`. Preserve network-free Decimal accounting, local
owner/CSRF boundaries, atomic balance/journal/idempotency, explicit closed-candle
fill semantics and fee-inclusive risk. Verify SHORT signs, collateral, duplicate
commands/signals, pre-entry OHLC look-ahead, ambiguous SL/TP, adverse gaps, stale
equity, restart recovery and Render ephemeral-disk disclosure. Auto Paper defaults OFF, permits only owner-enabled server-confirmed closed
signals, and never permits exchange writers or real-money override. See `../PAPER_TRADING.md`.

Review `app/paper/{auto,signals}.py`: causal cutoff before features, exact archive/
market tail match, atomic decision/trade/watermark, permanent dedup beyond audit
retention, one-open-position risk cap, explicit stops fallback, generations and
restart PAUSED. Bybit 403 must not be bypassed. See `../AUTO_PAPER_TRADING.md`.

## Strategy Lab research review

Review `app/lab/` and `docs/STRATEGY_LAB.md`. Check common calendar and complete
closed OHLCV, causal indicator prefixes, next-open signals, conservative gap/SLTP
fills, independent validation cashflows, Decimal fee-inclusive sizing and undefined
metrics. Never alter Aura to force shared execution compatibility. Prove Lab has
no Paper state/private exchange dependencies or activation route. Preserve bounded
fetch/CPU/storage, hashed snapshot/configuration/replay and explicit ephemeral-disk
limitations. Compare formulas independently of implementation fixtures.

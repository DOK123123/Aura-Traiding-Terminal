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

- Only the fixed official Testnet API and allowed GET endpoints are used. No
  production account fallback, order-writing methods, transfers or exchange keys
  in market ingestion. Public production quotes do not authorize real trading.
- HMAC key/secret stay server-side in environment variables; signed URLs, headers,
  exceptions and upstream bodies cannot disclose them. Redirects stay disabled.
- Configured account reads require owner access; absent keys mean Not configured
  with working market UI. Cache is bounded in freshness and failures hide old data.
- Timeout, invalid keys/data, clock errors, cooldown and temporary network loss
  have offline regression coverage. Test data is clearly dummy, never actual keys.

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

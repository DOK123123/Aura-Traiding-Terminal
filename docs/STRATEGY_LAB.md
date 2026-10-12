# Strategy Lab v1.1 — research only

Strategy Lab is independent of Aura signals, Auto Paper, the Paper ledger and
private exchange accounts. It never activates a strategy or submits exchange
orders. Start the application as before with `python start_web.py`. The new panel
requires the existing owner password `AURA_TESTNET_VIEW_PASSWORD` (Basic user
`aura`). Click Run explicitly; opening the terminal does not start research jobs.

## Honest Aura compatibility

Aura Existing is listed as **INCOMPATIBLE**, without invented metrics or ranking.
The unchanged historical-analog backtest uses its own horizon-20 close exit,
100% notional sizing and flat round-trip cost convention. Replacing these with
next-open execution, ATR protection and 1% risk would change Aura semantics.
Its native backtest remains available in the existing Historical Analogs panel.
This release provides three comparable experimental results, not four equivalent
backtests. No Aura formula, threshold or Auto Paper behavior is changed.

## Reproducible data and calendar

Only public Binance BTCUSDT spot klines are requested from the existing public
market-data HTTP client, through a bounded GET adapter pinned to
`https://data-api.binance.vision/api/v3/klines`. No credentials are used.
One 15m snapshot is aggregated exactly into 1h and 4h. All tests use the same UTC
4h-aligned evaluation start/end (end exclusive). Default coverage is 60 days;
250 4h candles of prior warm-up are fetched separately. Forming candles are
excluded; duplicates, disorder, gaps, malformed OHLCV and incomplete requested
history fail the run. Prices are never forward-filled. No fallback changes source.

The development fraction defaults to 70%, configurable 50–90%. The boundary is
rounded down to a UTC 4h boundary so every timeframe has identical split dates.
The report records requested and actual split, counts, source and coverage.
Validation indicators may use development history, but validation starts flat
with a new balance; development trades/cashflows never carry across. Every split
closes remaining positions at its final close. Parameters are frozen before
running both splits; no optimizer or validation-based parameter selection exists.

Snapshots, configuration, parameter sets, software version, algorithm hash and
Python version are stored alongside the complete report. IDs are content-derived.
Replay uses only the saved snapshot, verifies identical output and refuses a
changed algorithm/Python runtime. Export JSON contains the full auditable data.

## Fixed experimental defaults

| Strategy | Entry at closed candle | Strategy exit at closed candle |
|---|---|---|
| Donchian | Close breaks previous 20-bar high/low, excluding current bar | Break of opposite previous 10-bar channel |
| Trend + ATR | EMA50/EMA200 trend and close above/below EMA50 | Trend or price/EMA50 confirmation ends |
| EMA + RSI + ADX | EMA20/50 alignment, Wilder RSI14 ≥55 / ≤45, ADX14 ≥25 and directional-index alignment | EMA reversal, RSI crosses 50 or ADX <20 |

All use Wilder ATR14, SL distance 2 ATR and TP distance 4 ATR, measured from
actual entry fill. Indicators have explicit seeds/warm-up. Experimental indicators
are separate; they do not modify or import Aura's strategy implementation.

## Common execution and accounting

Baseline: 10,000 USDT, fee 10 bps per fill, adverse slippage 5 bps per fill,
1% fee-inclusive stop risk, maximum notional 2,000 USDT, one position, 1× virtual
collateral for both LONG and SHORT. These are research assumptions, not asserted
exchange fees. The UI can explicitly configure fee/slippage and split fraction;
other baseline settings and strategy parameters remain fixed in v1.1.

A signal observed at close can fill only at the next candle open. Pending signals
cannot cross a split boundary. Stop/target protection takes priority over pending
strategy exit at the opening price. Gap-through SL fills at the worse opening
price; gap-through TP fills conservatively at the target. If a candle touches
both, SL wins. Strategy exits fill next open; final segment liquidation fills
at final close. All fills apply adverse slippage and fees.

LONG gross PnL = quantity × (exit fill − entry fill); SHORT reverses the sign.
Net PnL subtracts both fees. Slippage is already in fill prices, not subtracted
again. Size is the minimum of stop-risk capacity, notional cap and cash/collateral
capacity, rounded down; rounded fees/risk are checked independently afterward.
Invalid/nonpositive net target reward is rejected. Equity marks open positions
using estimated adverse liquidation prices/fees. Money/fees use Decimal at
8 places, quantities 12 places, arithmetic context 64 digits; fees round upward.
Indicator math uses causal floating-point series, separate from money accounting.

## Metrics and ranking

Each timeframe has separate development/validation rows, complete trades and
equity curves. Zero trades/losses produce explicit null metrics where undefined;
profit factor is not fabricated as infinity. Realized risk/reward is average net win divided by average absolute net loss
(undefined unless both exist). Trades separately record planned target/stop
risk/reward and fee-inclusive entry risk. Win/loss averages and expectancy
use closed net trades; drawdown uses the recorded mark-to-liquidation equity path.

Validation ranking uses net return descending, then lower maximum drawdown,
then name for deterministic ties. Ranking eligibility requires at least 20 trades;
small samples are inconclusive. The best numerical result can be highlighted even
when ineligible, with an explicit caveat. No backtest declares safety/profitability.
Sharpe requires at least 20 trades and 30 complete UTC daily equity returns,
positive equity and nonzero sample variance; annualization is sqrt(365), zero
risk-free rate, crypto 24/7. Otherwise it is null with a reason.

## Storage, limits and Render

Separate SQLite: `.data/strategy-lab.sqlite3`, optional `LAB_DB_PATH`. Paper and
historical archive paths are forbidden, including resolved aliases/hard links.
Only the last 10 inserted experiments are retained; export before eviction.
Immutable full snapshots/configuration/results survive ordinary restarts while
the same filesystem exists. **Render Free ephemeral filesystem is not durable
across instance replacement/redeploy.** Export JSON externally; no paid service
has been added. Multiple replicas are outside this single-process design.

Limits: 12,000 source 15m candles including warm-up, 12 pages, 1 MB per page,
60-second total historical fetch, cooperative 30-second computation budget,
one research job and one stored-report read at a time, 25 MiB per decompressed
stored document. UI days 1–80; unsupported ranges fail visibly, never truncate.
Trade detail pages contain at most 100 rows; displayed equity is sampled to at
most 302 points with endpoints/extrema retained and labelled. Export is complete.
Transient source failures are explicit, not synthetic data. Actual Render CPU/
latency and public-endpoint availability remain unverified in this sandbox.

## Manual Render/Android checks

1. Existing charts, signals, Paper and Auto Paper states remain as before.
2. Owner login and Lab Run work; no run starts before clicking.
3. All timeframes show the same dates; development/validation switch accurately.
4. Aura is visibly incompatible; low-trade and undefined-metric warnings remain.
5. View paginated trades, equity, export, load saved experiment and replay.
6. On phone, controls fit, tables scroll, export downloads and errors are readable.
7. Missing owner password, source outage, busy job and long request show safe errors.
8. Restart with same disk preserves a saved study; redeploy may erase local studies.

No live Render/mobile or real historical fetch was performed during implementation.

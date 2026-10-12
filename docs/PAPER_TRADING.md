# Aura Paper Trading — virtual local ledger

**REAL MONEY EXECUTION = DISABLED. Auto Paper defaults OFF.**
Explicit owner-enabled Auto Paper is documented in [AUTO_PAPER_TRADING.md](AUTO_PAPER_TRADING.md).
This engine cannot submit exchange orders. Binance Testnet and Bybit Demo remain
separate GET-only integrations. No exchange key is needed by paper trading.

## Architecture and account access

`app/paper/models.py` validates settings and closed-candle inputs; `storage.py`
provides SQLite transactions/backups; `engine.py` contains network-free Decimal
accounting, risk gates, idempotency, protective exits and statistics. `market.py`
accepts an injected callback to the existing `/api/market` implementation.
`service.py` runs blocking SQLite operations in worker threads and checks protective
virtual exits every 15 seconds when positions exist. It never opens a position
from a strategy signal. No positions means no paper market requests.
`api.py` exposes owner-only local-ledger routes; `static/paper.js`/`paper.css`
provide a separate panel without changing existing indicators or charts.

Run the existing `python start_web.py` (one worker). Owner access uses username
`aura` and existing Render Environment Variable `AURA_TESTNET_VIEW_PASSWORD`
(minimum 12 characters, use a strong random password). Use HTTPS on Render;
HTTP Basic must not be used across an untrusted plain-HTTP network. Without an
owner password paper operations are closed; the market terminal still works.
Click **Войти: пользователь aura**, then return to the panel. No exchange
credentials are displayed or loaded by the ledger. Mutations require owner auth,
`X-Aura-Paper: local-only`, and same-origin browser requests; wildcard CORS is not
added. Responses and backup downloads are `no-store`.

GET: `/api/paper/state`, `/quote?symbol=BTCUSDT&timeframe=15m`, `/login`, `/export`.
POST (Aura local ledger only): `/positions/open`, `/positions/{id}/close`,
`/settings`, `/refresh`. These are not exchange requests. No exchange POST,
amend, cancel, funding, transfer or withdraw methods are added.

## Manual actions and fill model

1. Select a fresh BTCUSDT chart and timeframe.
2. Get a paper quote; verify source, closed-candle price and UTC time.
3. Choose LONG/SHORT, reason and optionally size/SL/TP; open a **paper** position.
4. Close it manually or let simulated protective SL/TP evaluate closed candles.

Only BTCUSDT is supported in this stage. Gold is quoted in USD; no USD/USDT
conversion is invented. LONG and SHORT both reserve 1× USDT notional. These are
virtual directional exposures, not Spot short borrowing or exchange margin.
There is no leverage, spread, normal execution slippage, funding or borrowing cost.
Do not interpret paper performance as an exchange-fill prediction.

Entry/manual exit price is the latest verified **closed candle close**, not the
forming candle, bid/ask or current WebSocket tick. Entry time is actual action
time; `entry_price_time` identifies the historical closed-price reference.
Prices inherit precision of the existing public float candle representation via
`Decimal(str(price))`; this does not recover digits lost upstream.

The backend rejects stale snapshots, malformed OHLCV, gaps, changed quote,
source mismatch and duplicate/out-of-order candles. Client entry quote binds
source/timeframe to the chart; backend rechecks identity and exact price/candle.
Existing freshness thresholds apply: snapshot fetched within 30 seconds,
last close no older than two intervals. Position marks must also be observed
within 30 seconds. Stale/mismatched equity is `null`, displayed as —; new entries
are blocked while an existing position cannot be valued reliably.

After restart, protective exits replay missed contiguous closed candles (at most
500 per read), never invented bars. If more history is missing, protective exits
pause with `MARKET_GAP`; a manual fresh close is explicitly marked
`MANUAL_HISTORY_GAP`, without claiming the unseen stops were checked. Source
changes pause the affected position. Same-time candle corrections are rejected.

Full candles after entry use high/low. The first candle overlapping a manual
entry uses close only, avoiding pre-entry high/low look-ahead. When both SL and
TP are touched, SL wins (`STOP_LOSS_AMBIGUOUS`). Adverse opening gaps fill SL at
the worse candle open. Favorable TP gaps conservatively fill at TP. Partial-bar
close-only exits use the close. Protective exit time is candle close, not an
invented intrabar timestamp; `processed_at` records when Aura handled it.
Stops are simulated, not guaranteed risk limits; gaps can exceed initial risk.
Service sleep or missing data can delay/disable protective processing.

A client-generated UUID request ID plus normalized-payload hash is stored in
SQLite in the same transaction as the trade. Retrying the same command returns
its existing trade even after restart or a market outage. Changed payload with
the same ID fails. Optional unique signal IDs cannot open duplicate trades.
Signal source is currently `MANUAL`, not a fabricated strategy recommendation.
If an action has an unknown outcome, UI retains that command in sessionStorage
(no credentials) across refresh, blocks new actions and offers an explicit retry
with the same ID. It never retries a trade automatically.

## Settings, risk and exact money calculations

Defaults (paper assumptions, **not an exchange tariff**):

| Setting | Default | Initial environment override |
|---|---:|---|
| Starting balance USDT | 10000 | `PAPER_STARTING_BALANCE` |
| Commission each side % | 0.10 | `PAPER_COMMISSION_PCT` |
| Risk per trade % | 1 | `PAPER_RISK_PER_TRADE_PCT` |
| Maximum position notional USDT | 2000 | `PAPER_MAXIMUM_POSITION_SIZE_USDT` |
| Maximum simultaneous positions | 1 | `PAPER_MAXIMUM_SIMULTANEOUS_POSITIONS` |
| Default stop distance % | 2 | `PAPER_STOP_LOSS_PCT` |
| Default target distance % | 4 | `PAPER_TAKE_PROFIT_PCT` |

Environment defaults seed a new database only. Later settings are saved through
the owner-only panel; they survive restart with that database. Starting balance
cannot change after the first trade. Existing trades retain their entry-time
commission and price levels. No reset endpoint or automatic-execution setting.

Amounts in API/SQLite are decimal strings, not JSON floats. Internal calculations
use Decimal precision 64. USDT monetary results are quantized to 8 decimals;
fees and reserved notional round up conservatively, ordinary price PnL uses
half-even. Base size floors to 12 decimals; explicit size with more digits fails.

For size `q`, entry `E`, exit `X`, fee percent `c`:

```text
fee(P) = ceil_8(P * q * c / 100)
gross price PnL = round_8((X - E) * q)       LONG
                = round_8((E - X) * q)       SHORT
realized PnL = gross price PnL - entry fee - exit fee
PnL % = realized PnL / reserved entry notional * 100
risk budget = fresh liquidation equity * risk_per_trade_pct / 100
planned loss at SL = ceil_8(abs(E - SL) * q) + fee(E) + fee(SL)
```

Auto sizing (manual action, not automatic trading) takes the minimum of risk
budget / fee-inclusive stop-distance-per-unit, maximum USDT notional / entry,
and available cash / fee-inclusive entry. Small rounding buffers are deducted
before flooring quantity. Every bound is then independently checked with actual
rounded fees. Manual quantity passes identical gates. Wrong-side SL/TP, fee-
negative target reward, max positions/notional, insufficient collateral or risk
violation reject entry without charging fees. Risk is per trade; concurrent total
exposure is additionally bounded by cash, max notional and max positions. There
is no claim of a portfolio correlation model or guaranteed gap loss cap.

Balance = starting balance + closed net PnL - entry fees of open positions.
Available balance = balance - reserved notional of open positions.
Equity = balance + open gross price PnL - estimated exit fees, when marks are fresh.
On close only gross PnL minus exit fee is added (entry fee was already charged).
SHORT opening does not credit fictitious sale proceeds. Severe gaps can leave
virtual equity/balance negative; further entry then fails, never external funding.

## Statistics and equity curve

Trade count/wins/losses/win rate use closed trades, including breakeven in the
win-rate denominator. Win/loss classification uses settled net PnL after fees.
`gross_profit` = sum of positive net trade outcomes; `gross_loss` = magnitude
of negative net outcomes, conventional aggregate strategy statistics. Per-trade
`gross_price_pnl` separately records movement before fees. Net PnL is all closed
net outcomes. Open entry fees also appear in current balance/equity, not falsely
as a closed loss. Profit factor = gross_profit/gross_loss; with no losses it is
`null` rather than an invented infinity. Missing win/loss averages and win rate
without closed trades are also `null`.

`risk_reward` is mean planned fee-inclusive TP reward / initial SL risk.
`realized_reward_risk` is average winning net PnL / average losing magnitude
when both exist. Current and maximum win/loss streaks follow **close order**;
breakeven resets both. Return uses current liquidation equity / starting balance.

Equity points record initial account, entries, exits, accepted new closed bars
and transitions to unavailable marks. Repeated same candle adds no duplicate
point. Curve gaps remain null and SVG does not connect across them. This is a
**sampled liquidation-equity** curve, not tick/intrabar or exchange equity.
Replay curve points evaluate marks at their historical candle close, with current
fetch freshness still enforced. Future trade cashflows/marks cannot enter those
points; unreconstructable historical portfolio points remain null.
Maximum drawdown compares sampled equity with its prior peak; peak and historical
maximum are persisted independently of response truncation. Multi-timeframe
marks are latest fresh observations, not a reconstructed synchronous tick book.
API returns last 500 curve points and last 100 closed trades with total/truncation
flags. Statistics cover the complete journal; full history is in backup.

## Persistence and Render

Default database: `.data/paper.sqlite3`, excluded from GitHub along with WAL/SHM.
SQLite uses WAL, FULL sync, foreign keys, `BEGIN IMMEDIATE` writes and per-operation
connections. Trades, balance, idempotency requests and curve updates commit
atomically. On startup the engine checks version, metadata/curve/command/index consistency,
stop/time alignment, accounting invariants, fees, closed PnL and PnL %. A corrupt/unavailable journal disables paper; it is **never silently
reset** to 10000. The market application can still start.

**Render ordinary local filesystem is ephemeral.** Page reload does not lose
history, and process restart with the same disk is supported; redeploy/restart of
an ephemeral Render instance can destroy the database. No paid disk or external
service has been provisioned. For reliable long-lived history, attach a persistent
disk yourself and set `PAPER_DB_PATH=/var/data/aura/paper.sqlite3` under its mount.
Use one service/worker; this is not a distributed execution engine. A free sleeping
instance cannot provide continuous SL/TP monitoring while asleep.

Without a disk, download `/api/paper/export` regularly using the panel link. This
is a consistent standalone SQLite backup, not just a JSON screenshot. For recovery,
stop the service, preserve the current database as a backup, replace the configured
DB with the downloaded file, remove only the old matching WAL/SHM while stopped,
then restart and validate balance/journal. Do not copy a live DB without its WAL;
do not upload backups into GitHub. No browser restore or destructive reset route
is provided. Browser sessionStorage is only pending-command recovery, not the
source of truth for balance or journal.

## Verification

```text
python -m pytest -q
node tests/test_frontend_reliability.cjs
node tests/test_testnet_frontend.cjs
node tests/test_bybit_demo_frontend.cjs
node tests/test_paper_frontend.cjs
node --check static/paper.js
```

Tests use disposable databases and mocked public reads; no exchange mutations or
real credentials. See `PAPER_TRADING_REVIEW.md` for checks, fixes and limitations.
After Render deployment manually verify phone layout, owner login, new paper
quote/manual open/close, SL/TP handling, fee totals, backup download, and restart
recovery only when persistent storage is configured. No live Render or exchange
account was accessed by the offline test suite.

Latest pre-Render audit and Android manual checklist: [AUDIT_RENDER_ANDROID.md](AUDIT_RENDER_ANDROID.md).

Auto Paper now supports separately opted-in server-owned signals, decision audit
and ALL/MANUAL/AUTO attribution. Earlier audit reports describe their pinned
pre-Auto snapshots. Generic arbitrary signal/exchange execution remains disabled.

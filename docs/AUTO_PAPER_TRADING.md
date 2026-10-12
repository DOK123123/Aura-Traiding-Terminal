# Auto Paper Trading — experimental virtual-only execution

**VIRTUAL FUNDS ONLY · REAL MONEY EXECUTION = DISABLED. Default OFF.**
No private account is required. Bybit Demo / Binance Testnet stay GET-only and
independent. Bybit 403 is not bypassed: no host change, proxy, VPN or production
account fallback. Auto Paper has no exchange execution client.

## Start / stop

1. Log into Paper as `aura`, using the existing Render owner-view password.
2. Select a fresh **BTCUSDT** chart and timeframe (1m / 5m / 15m / 1h).
3. Select SL/TP policy. Current strategy has **no SL/TP output**:
   - **SKIP** (default): reject directional entries with `STOPS_UNAVAILABLE`.
   - **PAPER_SETTINGS**: explicitly allow paper-only default SL/TP percentages
     from the existing risk settings. Defaults 2% / 4%; this is not a claim that
     the strategy generates these price levels. No hidden fallback is enabled.
4. Choose **ON / RESUME**, press Apply. Scope and source are pinned to that chart.
   Current latest close becomes activation baseline; only the next new closed
   candle can enter. Auto may frequently WAIT: thresholds are not optimized.
5. Choose OFF and Apply to halt new auto entries. Existing positions still get
   local protective SL/TP checks. Changing a chart alone does not silently retarget
   the armed scope; explicitly apply a new scope to change it.

States: OFF, ON, PAUSED, ERROR. Short public-data failures pause entries; a later
fresh coherent closed window may recover automatically. Missing replay history
requires explicit resume. ERROR, missing owner password and restart require manual
resume. ON/PAUSED/ERROR saved in SQLite restart as **PAUSED / RESTART_REQUIRES_RESUME**,
never silently trade on wake-up. OFF remains OFF. A new ephemeral deployment starts
OFF because no database/authorization survives. Enable retries are idempotent for
an already ON identical scope/policy; they do not reset its candle baseline.

## Architecture

```text
Service timer (15 s, independent of browser / exchange account)
  -> existing public market reader -> validate closed Window
  -> existing Paper Engine protective exits
  -> server SignalReader: existing historical archive, closed cutoff + tail match
  -> unchanged Historical Pattern evaluate + unchanged default PatternConfig
  -> Auto coordinator transaction: state/generation + watermark + risk + virtual entry
  -> SQLite trade/command/curve/decision/watermark commit together
```

`app/paper/auto.py` is network-free. `signals.py` accepts only an injected public
history callback and uses Aura `patterns.engine.evaluate`, `PatternConfig()`
defaults, context 500. No new strategy, UI-supplied signal, indicator formula,
threshold fitting, or backtest optimization. `service.py` never holds Bybit or
Binance private clients. Main injects the same public HTTP/history path already
used for research. Freshness/timeout failures produce fixed safe reasons.

Owner-protected GET `/api/paper/state?scope=ALL|MANUAL|AUTO` includes mode, last
candle/signal/action/rejection, retained decisions and auto statistics.
Local POST `/api/paper/auto` accepts only enabled, BTCUSDT/timeframe, expected
public source and explicit fallback policy. Authentication, same-origin custom
header, strict types and extra-field rejection apply. It accepts **no signal**,
credentials, exchange host, execution client or real-money setting.

The legacy `automatic_signal_execution=false` field / generic `handle_signal`
gate still prohibit arbitrary signal/exchange execution. The new explicitly
armed `auto_paper` state is the only Auto Paper path; the old flag is not the
Auto Paper status. All trades use `execution_mode=PAPER`, with `entry_type=MANUAL`
or `AUTO_SIGNAL`. Older journal trades without the tag are treated as MANUAL.

## Confirmed own signals and causality

SignalReader takes BTC closed history **only through decision candle close**;
future and forming candles are removed before features, matching, MTF aggregation
and historical outcomes. The closed market window must exactly match the archive
OHLC and available volume tail, same source/timeframe/symbol. Default historical
matching purges candidate forward horizons before the query, as before.
Only that server computation's LONG/SHORT can enter. WAIT means NO_SIGNAL.
Confidence is the existing evidence score, not a calibrated profit probability.

Entry fill is the existing verified **closed-candle close**, not WS bid/ask. Entry
time is actual processing time; signal timestamp and entry candle/reference time
are stored separately. No intrabar confirmation or historical backfill entries.
Missed contiguous bars are logged as `MISSED_CANDLE_NO_ENTRY`; only current fresh
latest decision may open. Protective exits can replay existing positions as before.
Same closed candle correction/source mismatch pauses processing rather than mixing
feeds. SL/TP use the unchanged conservative partial-bar / ambiguous / adverse-gap
rules. Sleep or missing history does not invent trades or protective outcomes.

## Risk and metadata

New-account defaults: 10000 USDT, 1% risk, maximum simultaneous positions 1.
Existing balances/settings are **not reset** during upgrade. Auto entry uses
`min(configured risk,1%)` and a **global one-open-position** cap while Auto is armed,
including manual positions. Existing excess positions are not forcibly closed;
Auto skips `POSITION_ALREADY_OPEN`. Max notional, available collateral, fee-inclusive
stop risk, quantity flooring, net-positive target, fresh equity and all current
Paper Engine validation remain in force. Manual risk setting is not silently
rewritten. Auto sizing consumes only virtual account balance.

SL/TP from a future valid strategy output can pass the same validation. Missing
levels are either explicitly paper-fallback or skipped. Invalid supplied levels
never receive a silent repair. Fees remain paper-configurable assumptions.

Each auto trade stores symbol/timeframe, direction, signal timestamp/confidence,
entry candle/price/time, size, effective risk %, commission, SL/TP, source,
market-data source, reason, strategy version `HISTORICAL_PATTERN_V1_DEFAULTS`,
stop policy and execution/entry labels, plus existing exit/PnL fields. Strategy
version pins this unchanged v1/default-policy contract, not a fitted parameter set.

## Atomic duplicates and decision audit

Candle identity = symbol + timeframe + candle-open UTC timestamp, independent of
provider label, signal direction or reconnect. UUID5 command ID and unique signal
ID derive from it. Auto decision, virtual open/fee, command record, curve and
per-timeframe high watermark share **one BEGIN IMMEDIATE transaction**. A failed
entry rolls back its savepoint but keeps the rejection log; a transaction failure
cannot commit only the trade or only its cursor. Configuration generation rejects
late computations from a previous OFF/ON/scope. A data failure from an obsolete
generation cannot pause a newly configured scope.

Persisted watermarks reject every same/older candle, including previously rejected
signals, across refresh/restart/reconnect/repeated REST and after audit rotation.
Existing unique trade signal IDs/commands provide additional lifetime dedup.
Resume treats the latest candle as baseline; previously consumed candles never
become new trades just because audit rows were deleted.

Audit logs candle-close/recorded timestamps, scope/source, real signal result or
null when not computed, confidence, ON/OFF/state, opened YES/NO, trade ID and fixed
rejection/action. Reasons include NO_SIGNAL, AUTO_OFF, STALE_DATA, MARKET_GAP,
SOURCE/TIMEFRAME/SNAPSHOT_MISMATCH, POSITION_ALREADY_OPEN, risk/funds/invalid stop
failures and explicit missed/baseline skips. Duplicate deliveries return without
appending repetitive audit rows; watermark remains authoritative.
Retention: maximum **2000 decisions**, maximum **30 days**, newest 100 in API/UI.
Watermarks (four supported BTC timeframes) are never rotated. Retention deletes
rows, not journal trades or dedup records; SQLite reuses free pages. VACUUM is not
run on each decision. The original complete trade/equity journal continues to grow;
this policy bounds the newly added decision log, not every database table.

## Statistics and migration

ALL is the real shared virtual ledger. MANUAL/AUTO filters trade outcomes, wins,
losses, PF, fees, streaks and journal; each also has an attributed balance/equity,
return and sampled drawdown curve based on the same starting balance. These are
**performance attribution slices, not separate spendable wallets**. Slice balances
must not be summed: the starting baseline is counted twice. Portfolio available
funds and risk checks always use ALL. Empty metrics / undefined PF stay null.

`curve_slices` stores MANUAL/AUTO valuation points transactionally alongside the
existing curve, with separate peak/DD. Legacy all-manual curve history is copied
into MANUAL, while AUTO starts at a constant original baseline. No backdated auto
trades are invented. Missing auto curve attribution fails closed rather than
rebuilding it from guessed history. Statistics/signal/UI are read coherently under
service locking; late ALL responses cannot repaint a selected AUTO view.

## Render Free / recovery / limits

Use existing `python start_web.py`, one worker. No new package, paid storage or
external account setup. Credentials are never read by Auto Paper.

SQLite survives page refresh and process restart **only if that database remains**.
Render Free disk can disappear on instance replacement/redeploy. In that case trade
history, statistics, watermarks and ON authorization are lost; the replacement
starts OFF. Do not claim dedup across destruction of the entire persistence layer.
No paid disk was provisioned. Download owner-only SQLite backups; optionally use
an already configured persistent `PAPER_DB_PATH`. Restored backups recover state
up to backup time only, and old backups cannot prove decisions made afterward.

Render sleep suspends timer/SL/TP; wake/restart requires resume if app restarted.
An in-process gap recovery skips old entries and replays only protective exits
within available coherent 500-bar history. Bigger gaps pause. History/snapshot
unavailable means pause/skip, not synthetic prices. Algorithm is closed-candle
paper experimentation without exchange spread/funding/leverage/slippage realism.

## Validation / manual Render checks

Offline tests cover entry LONG/SHORT, stop/target, commissions, independent money
oracle, sizing/risk, limits/balance, default OFF, explicit ON, PAUSED/ERROR, retained
state/backup, causal future/forming-bar exclusion, source/tf/stop errors, generation
races, transaction rollback, parallel/restart/reconnect/rotation dedup, filtered
statistics, UI modes/scope races and network-free exchange boundary.

All Python/Node, imports/syntax and static scans must pass before integration.
Separate architecture/Python/frontend/security/math/look-ahead/Paper/reliability/
testing review findings and actual results are in `AUTO_PAPER_REVIEW.md`.

Live Render/mobile not verified by offline tests. On Android check owner access,
OFF by default, visible virtual-only safety label, fallback selection and explicit
ON, fixed scope/last candle, WAIT/rejection logs, one entry per candle, OFF halting
entries, SL/TP journal, ALL/MANUAL/AUTO filters, background/reconnect UI and backup.
Restart after backup: PAUSED and no new trade until resume. Never enable production
permissions or try to bypass Bybit 403 for this experiment.

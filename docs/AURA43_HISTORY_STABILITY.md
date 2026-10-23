# Aura 4.3 — history pause and protective recovery

Scope: Bitget BTCUSDT USDT-M Futures PAPER only. No strategy, indicator,
risk-policy, commission, slippage, Aura 4.2, Practice, Worker or scheduler
configuration changes. No real exchange orders, production writes, deploy or
automatic initial activation are part of this release.

## Failure codes and safe diagnostics

| Code | Meaning |
| --- | --- |
| HISTORY_CANDLE_MISSING | The previously committed watermark candle is absent |
| HISTORY_CANDLE_CHANGED | Its full OHLCV SHA256 differs from the committed hash |
| HISTORY_SOURCE_UNAVAILABLE | Full history request failed; source error is retained separately |
| HISTORY_INCOMPLETE | The requested history is incomplete or contains a gap |

Specific region/access, clock, stale-data and contract-filter codes are retained;
they are not mislabeled as a generic network failure. The old combined code is
recognized when loading an existing PAUSED account, so it can safely retry.

Committed ERROR events and `ACTIVE43_STATE` application logs contain the reason,
underlying source error, UTC epoch timestamp, fixed market source, detection time,
old/new OHLCV hashes and scheduler run ID. If a candle was not received, its new
hash is null. Unknown gap timestamps/hashes remain null; they are never invented.
STATE_TRANSITION events and `last_status_transition` preserve mode, cause, time
and run ID atomically with the tick. Owner controls use their control request ID.
No credentials, raw upstream errors, headers or private payloads are logged.

## Separate entry and protection gates

A history discrepancy clears pending entries/strategy exits and prevents new
entries. The original watermark and its hash stay pinned until verified again.
An existing position and its SL/TP are not discarded.

For protection, use the same validated full snapshot when possible. If full
history cannot be obtained, fetch a separate 12-candle window through the fixed
public Bitget Futures GET client. It independently checks exchange time, response
freshness, identity, interval alignment, closed bars and continuity. It performs
no strategy analysis, trailing-stop changes or new entries.

The existing Decimal SL/TP, costs and accounting functions process eligible
closed bars after the position's entry and protection cursor. Ambiguous SL/TP
still resolves to SL first. `protection_watermark` is committed with the balance,
position, CLOSE and tick receipt. A retry/restart never replays the same close.

When no fresh trustworthy window is available, retain the position and show
`EMERGENCY_UNTRUSTED_DATA`; do not execute a stop using stale/cached prices.
Fresh protection can run while new entries remain PAUSED.

If the small window does not cover the entire outage, record `protection_gap`
and show `FRESH_PROTECTION_GAP`. Only observed candles are used. Unknown prices
and possible stop touches during the gap cannot be reconstructed or certified.
This is a limitation of candle-based virtual stops, not an exchange stop order.

## Recovery

Recovery is armed only by a previously ON/recoverable PAUSED state. Each retry
requires a complete fresh history and the **original** committed candle hash.
A continuing correction is not automatically accepted as a new baseline.
If protected candles have already advanced, resume from a verified current
baseline without replaying entries or closes. A new closed candle is required
before a new strategy decision can be queued from that baseline.

OFF and EMERGENCY never automatically become ON. STOP revokes recovery permission.
Risk guards can prevent automatic recovery and continue to prohibit entries.
If the old anchor has permanently changed or left the available history window,
the history pause intentionally persists. A separate explicit owner START on an
empty account can establish a new verified baseline using the existing controls.
There is no automatic acceptance of a changed hash or new recovery endpoint.

## Owner Panel

Inside **AURA 4.3 ACTIVE PAPER v3 · BITGET FUTURES**, directly below the existing
metrics, four fields show:

- PAPER/scheduler health: PAPER_ON, PAPER_PAUSED_HISTORY, PAPER_PAUSED_DATA,
  PAPER_OFF or SCHEDULER_ERROR.
- Existing-position SL/TP protection and an explicit untrusted-data emergency.
- Age of the last actually verified closed candle.
- Last persisted mode transition, reason, time and run ID.

Persisted mode is separate from delivery health. A stale heartbeat shows
SCHEDULER_ERROR without fabricating an OFF transition. A stopped process cannot
write its own failure to the DB; the next read calculates delivery health.
`last_successful_run_at` remains separate from `last_run_at` and market freshness.
Frontend ageing hides stale PnL and invalidates a stale protection indication.

## Storage compatibility and deployment

**No SQL migration, new tables, new environment variables or account reset.**
The existing hashed JSON envelope and atomic commit RPC accept the additional
optional metadata/event kinds. Existing accounts without new fields still load.
The existing strategy-selector SQL remains unchanged; preserved old diagnostic
timestamps do not become a cursor for a different strategy. Explicit START
clears recovery metadata before creating that strategy's activation baseline.

Deployment is manual and requires owner approval:

1. Inspect the existing owner read-only readiness and current position. For an
   empty account, leave PAPER OFF through installation. Preserve/export existing
   account/event records using the normal backup policy; never initialize/reset.
   If a position is open, plan continuity of the protective scheduler first.
2. Review/merge the fix only after required tests and reviews, then manually
   deploy the chosen commit in Render. Keep environment/secrets and Cloudflare
   saved_mode unchanged. There are no production SQL steps.
3. Check Owner Panel, backend health and two distinct automatic saved tick
   receipts. Confirm persisted mode, position, pending state and unchanged
   financial history. With an empty OFF account both deliveries must retain
   OFF and create no OPEN/CLOSE. Do not enable PAPER merely to make a test pass.

After separate approval to trade virtual funds, enable through the existing
owner control. Verify natural SIGNAL → OPEN → POSITION_UPDATE → CLOSE and
persisted money/events. No real signal means WAITING_FOR_REAL_SIGNAL, not a
failure and not a verified production trading cycle.

During a transient outage, check pause reason, protection freshness and atomic
events. After the original history returns, verify recovery only when authorized
and risk guards permit. After Render restart, compare the same position ID,
balance, mode, watermarks and event counts. A repeated five-minute slot must not
add a second OPEN/CLOSE. Do not inject fixtures or break production data to test.

Emergency action: existing owner STOP/EMERGENCY prohibits entries; protective
ticks are still needed for an existing virtual position. Disabling the scheduler
also stops virtual SL/TP monitoring. Free Render/cron delivery has no 24/7 SLA;
this code cannot prevent infrastructure sleep or prove continuous delivery.

## Rollback

There is no schema rollback or data deletion. Prefer rollback only with an
empty OFF account and no pending operations. Deploying the previous application
can restore its known history-blocks-protection defect: do not roll back to it
with a history-affected open position. Keep the protective version or fix forward.
Never reset money/history or replace stored hashes as a rollback technique.

## Reproducible checks

```sh
python -m pytest -q
node --test tests/*.cjs
python -m scripts.verify_active43_postgres --output /tmp/active43-history-sql.json
```

The last command creates and removes a restricted, disposable real PostgreSQL
container with no network or exposed ports. No production DSN/keys are accepted.
The HTTP bridge executes actual SQL RPCs locally; it is not hosted Supabase,
Render or Cloudflare proof. Synthetic signals exist only in offline fixtures.
Native indicator LONG/SHORT cycles and Bounce tests remain separate from them.

See `AURA43_HISTORY_STABILITY_VERIFICATION.json` for final results and separate
code/security review outcomes. Production autonomous execution remains unverified
until real deployed logs establish it. No claim of profitability is made.

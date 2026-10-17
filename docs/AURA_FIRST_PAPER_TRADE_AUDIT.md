# AURA — FIRST PAPER TRADE: audit and acceptance gates

Audit date: 2026-10-17 UTC. Base: main
`c50fd0bb2402bd261089142c96d4e9981f4594ab`, rechecked against GitHub.
Implementation remains in Draft PR #12, directly on main. No Research Lab
PR #3–#11 is included. This follow-up adds audit evidence and a regression test;
it does not change runtime trading code.

## What actually prevented a first trade?

There are two separate questions:

1. **Manual isolated PRACTICE on Render is currently unavailable.** A public,
   unauthenticated GET probe returned health 200, Auto42 status/alignment 401
   with an owner challenge, and `/api/practice/state` **404**. The checked
   deployment does not expose that route. The implementation is still a Draft
   PR; it has not been merged or deployed by this task. Dedicated Practice SQL
   and environment configuration also remain unverified on Render/Supabase.
2. **The previously reported automatic rejection is a strategy gate.** The UI
   text `Таймфреймы не согласованы` maps exactly to `MTF_NOT_ALIGNED`.
   `app/automated/strategy.py::_evaluate` returns direction `None` when
   `known_mask != 3 or not alignment`. Production context sets alignment only
   when all three nonzero EMA20/EMA50 directions agree and both higher frames
   are known. That result cannot create a pending entry. It does not demonstrate
   an execution or database failure because no OPEN was requested at that step.

**CURRENT_LIVE_AUTO_BLOCKER = NOT_ESTABLISHED_WITHOUT_OWNER_EVIDENCE.**
No current private production state, indicator snapshot, scheduler log, deployment
commit or Supabase trade record was available. HTTP 401 confirms protection,
not correct signals or healthy storage. The old reason alone cannot establish
whether today's inputs are legitimately conflicting, stale, missing or
inconsistent. Zero trades alone cannot establish a broken engine. No claim is
made that a production execution defect was found or repaired.

The public probe is recorded in `AURA_FIRST_PAPER_TRADE_ROUTE_PROBE.json` with no
response bodies, credentials or private production data.

## Actual automatic path on main

| Stage | Existing code | Behavior relevant to no trades |
|---|---|---|
| Trigger | `scripts/auto42_scheduler.py`, `app/automated/api.py::tick` | Separate scheduler token; 5-minute run-slot deduplication. Health or an open browser is not a scheduler tick. |
| Market | `app/automated/service.py::snapshot`, `market_data.py`, `app/intelligence/market_context.py` | Validated BTCUSDT public source and exact closed 15m tail/hash; only already closed 1h/4h context, no future candle. |
| Trend | `research/market_intelligence/structure.py::segment_states` | EMA20 greater/less than EMA50 determines +1/-1, equality gives 0; 250-candle warm-up in each segment. |
| Decision | `app/automated/strategy.py::_evaluate` | MTF alignment, directed retest, ADX >=25, regime, liquidity, confirmed BOS/CHoCH plus directed breakout within eight bars, volatility 0.65–2.0, opposing-level and stop checks. Rejection has no direction. |
| Activation | `app/automated/service.py::control` | Explicit START records an activation baseline; it does not immediately trade a historical signal. No control call was made in this audit. |
| Pending | `app/automated/engine.py::advance` | On a newly processed candle, an accepted decision becomes `SIGNAL_QUEUED_NEXT_OPEN`, persisted with its watermark. |
| Fill | `advance` → `open_virtual` | Pending is consumed when the next closed candle becomes available, using that candle's open with adverse slippage. This is delayed virtual next-open accounting, not a contemporaneous exchange fill. Missing multiple candles cancels pending; no retrospective missed entries. |
| Risk | `risk_reason`, `open_virtual` | Existing 0.5% fee-inclusive stop risk, one position, 2% daily loss, 10% drawdown, 2,000 USDT notional, balance and positive net target checks. Invalid next-open stops reject execution. |
| Exit/PnL | `protective`, `mark`, `close_virtual` | LONG/SHORT Decimal accounting, both-side fees/slippage, conservative SL-first ambiguous candle, adverse stop gaps. Protective exits are evaluated separately from permission for new entries. |
| Commit | `app/automated/service.py::_tick`, `app/automated/storage.py`, `scripts/auto42_schema.sql` | State, watermark, events and tick key go through revision/CAS commit. Non-concurrency storage errors propagate; a failed commit is not a successful saved opening. Restart loads persisted state. Actual PostgreSQL transaction behavior was not exercised here. |
| Evidence | `/api/auto42/status`, `/alignment`, `/live-monitor`, `/journal` | Owner-only reads of saved state, actual decision snapshot and execution records; diagnostics do not manufacture signals or rerun a different strategy. |

Data errors can pause entries, and risk/emergency/owner controls can block them.
The existing service only automatically re-arms its documented retryable data
failures when the saved recovery flag and risk checks permit it. A process restart
alone is not proof of lost state or an instruction to reset/re-arm an account.

## How the owner can establish the exact current automatic blocker

Authenticate in the existing terminal owner view (Basic username `aura`, existing
owner password), then inspect these **GET-only** URLs on the same Render host:

1. `/api/auto42/status`: mode, `diagnostics.block_reason`, last decision/error,
   scheduler success time, closed-candle watermark, storage status, pending and
   position. Check timestamps in UTC against the current closed candle.
2. `/api/auto42/alignment`: saved `snapshot.frames`, EMA values, close timestamps,
   known mask, alignment flag, actual condition, `decision_valid`, verdict and
   code identity. `VALID_ALIGNMENT_REJECTION` with current, consistent evidence
   supports legitimate disagreement. Missing/stale evidence or inconsistent
   inputs requires investigation; it does not authorize weaker filters.
3. `/api/auto42/live-monitor` and `/api/auto42/journal`: correlate SIGNAL/DECISION,
   rejection, pending, OPEN/CLOSE, run/candle/position IDs and storage errors.
   Paginate journal when necessary; a recent limited page is not full history.

Keep returned owner data private. Do not publish balances, positions, passwords
or service keys in a public issue/PR. Do not invoke START, RESET or tick merely
to collect evidence. If a pending signal exists but no OPEN, distinguish the
next-candle wait, missed candles, risk/stop rejection and storage failure by the
saved events before proposing a fix. No such live diagnosis is asserted here.

## PRACTICE implementation and verification

See `PAPER_PRACTICE.md` for the complete owner runbook and SQL proof queries.
The implementation reuses the unchanged `app.automated.engine` on a separate
10,000 USDT training state. Manual owner commands are explicitly labeled
`MANUAL_PRACTICE_NOT_STRATEGY_SIGNAL`; no signal is inserted into Auto42.
Fresh fixed-source Binance public trades are required. No exchange order API
is present. The browser cannot choose position size or bypass owner/CSRF/risk.

Separate `aura_practice_*` tables/RPCs persist state and append-only events.
Command UUID/hash, position-ID close, revision/CAS, row locking, database-clock
quote freshness and durable receipt read-back guard retries/concurrency.
No failed/uncertain database response is presented as a confirmed opening.
Protective quote sampling runs independently while the web process is awake;
the existing production scheduler remains unchanged. Sampling can miss touches
between observations or during sleep/outage, and gap losses can exceed planned
risk. A real PostgreSQL/Supabase acceptance test remains required.

The new offline regression `tests/test_first_paper_trade_audit.py` runs the real
strategy, service, engine and isolated temporary SQLite ledger: conflicting
frames persist MTF_NOT_ALIGNED with no pending/position/fee; a later aligned
fixture persists pending, the next candle opens exactly once, and a repeated
tick cannot open twice. Fixtures are not market evidence or production signals.
Existing Practice checks cover LONG/SHORT manual/TP/SL, independent Decimal
PnL, stale/missing quotes, failures/recovery, lost acknowledgements, restart,
concurrent commands, owner/CSRF/schema and balance isolation. Browser testing
uses explicitly offline quotes and mock Supabase RPC, never live substitution.
Current rerun results are in `AURA_FIRST_PAPER_TRADE_TEST_RESULTS.json`.

## Safe owner sequence after review — no deployment performed

1. Review Draft PR #12 and the additive SQL. Test its PostgreSQL/RPC grants,
   duplicate commands, locking, stale revision and rollback in an isolated
   Supabase environment first. No current trading table is migrated or reset.
2. Explicitly authorize merge/deploy later and arrange Render Auto Deploy so
   neither occurs without approval. Keep Practice disabled initially. Configure
   only dedicated `AURA_PRACTICE_SUPABASE_URL` and
   `AURA_PRACTICE_SUPABASE_SERVICE_KEY` plus the existing owner-view password.
   A separate project gives stronger credential isolation; shared service-role
   keys have broad project privileges despite namespace separation. No paid
   resource has been created; quotas and awake-process requirements apply.
3. Deploy the reviewed commit only when authorized, using `python start_web.py`
   with one worker. Check terminal health, Auto42 ticks and existing positions
   before enabling `AURA_PRACTICE_ENABLED=true`. Do not change scheduler or risk.
4. Open `/api/practice/login`, Connect, verify fresh quote and dedicated storage,
   enter sensible SL/TP, then OPEN LONG or OPEN SHORT. For unknown outcomes retry
   the same saved UUID. Verify receipt, chart, size, fee and UPDATE; CLOSE and
   match the same position's OPEN/CLOSE in Supabase using the runbook queries.
5. Verify checksums, exactly one OPEN/CLOSE, final PnL/balance and persistence
   after an authorized restart. Check browser-closed protective monitoring and
   open-position recovery separately. Never inject a fake production quote.

**RENDER_PRACTICE_VERIFIED = FALSE**

**REAL_SUPABASE_CYCLE_VERIFIED = FALSE**

**LIVE_AUTONOMOUS_EXECUTION = NOT_VERIFIED_BY_THIS_AUDIT**

A manual Practice cycle proves that isolated manual path only. Even a successful
Render Practice OPEN/CLOSE cannot set Auto42 LIVE AUTONOMOUS EXECUTION=VERIFIED;
that requires recorded natural strategy/scheduler OPEN and CLOSE on Render.

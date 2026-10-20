# Aura 4.3 Bitget: safe account initialization and OFF scheduler verification

## Exact cause of production NOT_INITIALIZED

[Diagnostics #16](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39394097695)
confirmed real Render authentication, Bitget CONNECTED, Supabase history RPC and
account SELECT working, valid configuration and enabled server module. The account
SELECT returned no row. The SQL migration creates tables/functions but intentionally
never seeds a portfolio. Read-only diagnostics intentionally never calls `load`.
The existing initializing paths (`status/load` or a permitted tick) had not made an
account available; scheduled runs #14/#15 were skipped. No strategy/risk change is
required, and no synthetic trading signal can solve this setup condition.

The correct remedy is an explicit account initialization, not enabling trading,
loosening risk or making read-only diagnostics write.

## One explicit preparation command

Actions operation **initialize**, implemented by:

```text
python -m scripts.active43_scheduler --initialize
```

The workflow uses the already configured separate scheduler token, even while
`AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED=false`. Default operation remains
**diagnostics**, read-only. Scheduled `tick` remains opt-in and its cron is unchanged.

The command performs four authenticated requests:

1. `/api/active43/diagnostics/scheduler`: real Bitget/Supabase connectivity preflight.
2. `/api/active43/initialize`: existing `aura_active43_bitget_load` RPC, only if the
   account is absent; read back through GET and validate checksum/scope/config.
3. `/api/active43/verify-off-tick`: existing production tick path with mandatory
   OFF/empty-account/risk guards, SQL CAS and immutable receipt readback.
4. `/api/active43/diagnostics/scheduler`: fresh postflight; require scheduler ACTIVE,
   connections confirmed and mode OFF before reporting PREPARATION_VERIFIED.

The two setup endpoints require the dedicated scheduler token and exact confirmation
`INITIALIZE ISOLATED PAPER ACCOUNT`; arbitrary amounts, signals, actions or namespace
fields are rejected. No public unauthenticated write endpoint or manual signal API.

## Account creation safety

- Reuses `scripts/active43_bitget_schema.sql`; **no new SQL migration, secret,
  environment variable, reset or paid resource**.
- Existing SQL validates new seed balance/equity 10000, mode OFF, position null,
  correct Bitget source and version; uses `INSERT ... ON CONFLICT DO NOTHING`.
- Idempotency and concurrent initializers are resolved by PostgreSQL singleton
  primary key, not a process-local lock. No blocking owner-control lock is held
  during market probes. Existing account balance/mode/position is read, never reset.
- The RPC does not say which concurrent caller inserted; response honestly reports
  `initialization_attempted`, not a fabricated per-request `created` count.
- Failure/timeout/readback uncertainty never reports success. Repeating preparation
  is safe: the account is read back, not recreated or reset.
- Existing ON/PAUSED/EMERGENCY account or open position is preserved. The CLI stops
  before heartbeat if it is not empty OFF. No owner STOP/START is sent.

## Why the OFF heartbeat cannot trade

It has a separate task, never reuses the ordinary scheduler task. The production
`Service._tick(require_off=True)` checks saved OFF + no position/pending/pending-exit/
recovery before data processing, before every CAS retry, and validates returned
mode/orders after the commit. Existing risk/emergency blocks remain enforced.
There is no snapshot/strategy/advance call in this guarded empty OFF path.

If an owner START wins concurrently, CAS fails and the next guard rejects ON;
verification cannot turn into a trading cycle. A duplicate committed tick is read
back, not executed twice. It writes a real OFF TICK receipt, not a fake OPEN/CLOSE
or an invented signal. Only monitoring metadata/journal changes; balances,
positions, fees, PnL and existing trades remain unchanged.

`Scheduler=ACTIVE` then proves a recent saved tick, not permanent periodic work.
No scheduled trading variable or persisted ON state is enabled by preparation.
Free Render sleep and GitHub scheduling delays still prevent a 24/7 guarantee.

## Minimal owner procedure after PR review

1. Approve/publish this PR and on [Render Dashboard](https://dashboard.render.com/)
   use **Manual Deploy → Deploy latest commit**. Keep PAPER OFF. The agent did not
   merge/deploy or apply production SQL.
2. Open [Aura 4.3 Actions](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml)
   → **Run workflow → operation=initialize → Run workflow**.

Expected: `ACTIVE43 PREPARATION_VERIFIED`, `account_available=true`,
`readback_verified=true`, `off_scheduler_tick_saved=true`, initial balance match
true for a new account, `auto_paper_enabled=false`, `production_paper_verified=false`.
In Owner Panel, **Обновить** reads the actual Supabase balance 10000 and mode OFF.
No need to copy SQL, keys or new settings. Repeating initialize is safe.

Until Render has the new routes, preparation reports `SETUP_API_NOT_DEPLOYED` and
stops; it never falls back to an unrestricted tick or a trading endpoint.

After this passes, any future decision to enable regular scheduling and START
PAPER is separate. A fresh authenticated OFF heartbeat does not establish a
natural production SIGNAL → OPEN → UPDATE → CLOSE or profitability.

## Verification and limitations

See `AURA43_ACCOUNT_PREPARATION_RESULTS.json` for actual counts and code/security
review. Tests use isolated synthetic market fixtures and disposable PostgreSQL:
concurrent initialization, idempotency, database restart, no balance reset, LONG/
SHORT existing-position preservation, emergency guard, concurrent START CAS,
OFF tick deduplication, HTTP authentication and exact request confirmation.
Existing LONG/SHORT TP/SL execution regressions also run against real local SQL.
Legacy account/event and SQL-function hashes remain unchanged.

Local HTTP-to-real-SQL tests are not hosted PostgREST/Render verification. No
production account creation is claimed until the deployed initialize endpoint and
its stored readback actually succeed. No real exchange orders or private exchange
credentials are involved.

## Actual GitHub/Render setup attempt

[Actions #17](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39397073669)
accepted the new explicit initialize operation from this branch. Real Render
preflight confirmed Bitget/Supabase CONNECTED and account NOT_INITIALIZED. The
next request returned HTTP 404, `SETUP_API_NOT_DEPLOYED`, at phase INITIALIZE.
Public Render OpenAPI also confirms the two new routes are not deployed. The
unrestricted trading step was SKIPPED. No production account creation, heartbeat
or balance/position change is claimed. The remaining gate is publishing the
reviewed server code, not another token, SQL or risk-setting change.

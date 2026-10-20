# Aura 4.3 Bitget: manual tick without enabling the periodic scheduler

## Cause of run #20

Run [#20](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39412966654)
used `workflow_dispatch` on main `08ff508ff52a61d270ac8d9032e99f06f2fdc309`.
GitHub reports the only job `active43_tick` as `skipped`, with no steps and no
runner assigned. No Python script ran and no request reached Render.

The old job condition allowed manual `diagnostics` and `initialize` directly,
but required `vars.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED == 'true'` for manual
`tick` as well as scheduled events. Thus a manual tick was skipped when periodic
scheduling was disabled or the variable absent. This is an Actions routing defect,
not a strategy rejection, HTTP authentication failure, or an uninitialized account.
GitHub's repository-variable metadata endpoint returns 403 to this session;
no claim is made to have read its stored value through that API. The corrected
workflow reports the effective periodic opt-in as a non-secret boolean.

## Fix and safety

- Explicit dispatches of `diagnostics`, `initialize`, and `tick` bypass only the
  periodic schedule opt-in. They do not bypass server authentication or risk gates.
- Scheduled events still require the exact string `true`; cron is unchanged.
- New manual `tick_policy` defaults to `off_only`. The CLI uses the existing
  authenticated `/api/active43/verify-off-tick` endpoint with its fixed confirmation.
  The server requires an initialized empty OFF account and checks it again after
  conflicting writes. It executes the existing tick persistence path without
  strategy evaluation, market snapshot, position execution, or account creation.
- The CLI requires the Bitget v3 scope, `state_saved=true`, `verification_only=true`,
  mode OFF and zero opened/closed positions before reporting success. Errors never
  fall back to `/tick`. Bounded retries use only the same guarded endpoint.
- Explicit `saved_mode` uses the existing `/tick`: it can execute virtual trades
  only if the owner has already enabled Paper in the saved account. It does not
  change ON/OFF. Do not select this option merely to verify preparation.
- Missing policy from older dispatch clients is interpreted as `off_only`.
  Unknown tick policies fail before HTTP; user input is passed through environment
  variables, never interpolated as executable shell/Python source.
- Existing token, fixed Render URL, concurrency group, checkout SHA, read-only
  GitHub permissions, timeouts and server protections are preserved.

No server, SQL, UI, strategy, risk, Aura 4.2, Paper Practice, balance or position
code changes. No secret changes or production SQL are needed. This change needs
**no Render redeployment**: the protected endpoint was already deployed with PR #20.

## Owner steps after review/merge

1. Merge the reviewed PR when satisfied. Open
   [Actions](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml),
   select **Run workflow**, branch **main**.
2. Select `operation=tick`, leave `tick_policy=off_only`, and run. Expect a completed
   job and `OFF_TICK_VERIFIED: saved=true mode=OFF opened=0 closed=0`. Then run
   `operation=diagnostics`: expect Bitget/Supabase CONNECTED and Scheduler ACTIVE
   while the heartbeat is fresh (360 seconds).

Keep periodic scheduling disabled and Paper OFF during this verification. A
heartbeat updates only scheduler metadata and its deduplicated TICK journal/receipt
in the isolated Active43 account. It does not reset the 10,000 USDT balance or
create trade history. A later process reads the committed account through the
existing Supabase RPC/readback path; no local runner file acts as storage.

If mode is ON, a position/pending order exists, an account risk guard is active,
or the database fails, `off_only` must fail safely; do not bypass the rejection.
No new initialize action is required for the already initialized account.

## Verification and review

See `AURA43_MANUAL_TICK_RESULTS.json` for actual test counts and Actions evidence.
Local PostgreSQL verification uses a disposable PostgreSQL 16 database, not
production Supabase. It checks migrations, RLS, real SQL transactions, concurrent
initialization, deduplication, OFF heartbeat persistence, database restart/readback,
LONG/SHORT SL/TP cycles and unchanged legacy accounts/functions.

Code review: traced event/job/step selection, exact schedule opt-in, existing
server commit/receipt/recovery paths and OFF account race checks. No execution
engine, strategy or accounting changes. Security review: token remains injected
only into HTTP operation steps; no values/hashes logged, fixed authenticated
Render endpoints, redirects disabled, no private exchange API, no control route.
No unresolved critical/high findings in the intended diff.

Production OFF heartbeat evidence is not autonomous trading evidence.
`production_paper_verified` remains false until a natural authorized production
SIGNAL → OPEN → CLOSE is recorded. No trading is enabled, merged or deployed by
this task.

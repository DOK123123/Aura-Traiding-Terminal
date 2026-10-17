# AURA PAPER PRACTICE — implementation and owner runbook

**RENDER_PRACTICE_VERIFIED = FALSE**

**REAL_SUPABASE_CYCLE_VERIFIED = FALSE**

This Draft PR is based directly on main `c50fd0bb2402bd261089142c96d4e9981f4594ab`. Research Lab PRs #3–#11 are not included. No merge, deploy, production quote substitution, exchange order or production database write was performed. Do not describe the implementation as ready on Render until the owner's actual durable OPEN → UPDATE → CLOSE cycle is recorded there.

## Implemented

- Owner-only `/api/practice/login` and `/static/practice.html`, with OPEN LONG, OPEN SHORT, CLOSE POSITION and explicit retry of an uncertain command.
- Dedicated live-quote chart with Entry / SL / TP lines, size, entry fee, total fees, liquidation-cost-aware current PnL, available cash, durable revision/save time and recent OPEN / UPDATE / CLOSE history.
- Fixed Binance Spot public GET `/api/v3/trades?symbol=BTCUSDT&limit=1`, using the same public market-data host already used by the terminal. No exchange key, provider switch, signed request or exchange writer. Missing, malformed, regressing, more than 10-second-old or more than 2-second-future quotations block execution. Public API errors/region restrictions fail closed; no invented quote fallback.
- Existing `app.automated.engine.open_virtual`, `close_virtual`, `mark`, `validate` and `risk_reason` are reused unchanged. No second execution engine or strategy signal is created. A manual quote adapter uses actual observed prices, not a fabricated OHLC candle or historical backtest signal. This is the existing Aura 4.2 virtual execution engine, not a new strategy.
- Separate 10,000 USDT account, PRACTICE-prefixed position IDs, `practice_scope=PAPER_PRACTICE_V1`, and dedicated Supabase tables/RPCs. No access/fallback to Aura 4.2, legacy Paper or Forward tables.
- Existing engine policy: at most one position, risk at most 0.5%, daily loss 2%, max drawdown 10%, nominal at most 2,000 USDT, 0.10% fee and 0.05% adverse slippage each side. Size is calculated by the engine, not supplied by the browser. Manual SL/TP must bracket both the current quote and slipped entry; reward must remain positive after costs. No settings/reset/strategy/scheduler control is exposed.
- Independent protective task checks quotes about every 3 seconds while the web process is running, including when the browser is closed. It cannot create entries. Existing Aura scheduler, secrets and frequency are unchanged. PRACTICE is disabled by default; without complete dedicated configuration it has no task, quote client or store.

## Persistence and command safety

New optional SQL: `scripts/practice_schema.sql`. It creates only `public.aura_practice_account`, `public.aura_practice_events` and `aura_practice_*` RPC/trigger functions. Existing trading tables/functions are not altered. Owner must review/apply it manually; the application never migrates, truncates or resets a database.

The account is initialized once with 10,000 USDT. Restart loads its existing state/position. Initialization uses INSERT ON CONFLICT DO NOTHING; changing environment variables cannot reset a saved portfolio. Events are append-only, RLS enabled, public/anon/authenticated access revoked, RPC execution restricted to service_role. The project URL and service key remain server-side in dedicated variables. A separate Supabase project/key provides the strongest credential isolation; using a shared project is supported through separate tables, but a service-role credential itself has broad project privileges. Never put it in browser code or logs.

Commands use a canonical UUID and a digest of action + body. The server checks the persisted receipt before fetching a new quote. Same ID/same body returns the existing receipt/current state; same ID/different body is rejected. The SQL transaction locks the account, checks expected revision, atomically appends the event and updates state. Duplicate handling also compares command hashes across different server processes. A stale concurrent revision cannot overwrite another command. The database checks quote age again on its own clock after acquiring the row lock.

A response is confirmed only after commit plus persisted receipt/state read-back. Timeout/database error/invalid response means **unconfirmed/possibly unknown**, not "opened". The browser preserves the same pending request in localStorage and retries its exact body/UUID. It does not auto-generate a new order after a lost response. A definitive rejection permits correction; it never creates a trade optimistically. CLOSE includes the exact expected position ID, preventing a delayed click from closing a different position.

The browser displays only database-backed state. The journal keeps command IDs, position IDs, UTC times, source, fees, prices, size and close reason. History UI is the latest 100 events, explicitly partial; full records remain in the dedicated table. No API key/secret is exported in responses.

## Limits that must remain visible

- No real Render or Supabase was connected in this task. The PostgreSQL migration was reviewed but **not executed against PostgreSQL/Supabase** here. Offline tests simulate RPC/transactions with SQLite; they are not a PostgreSQL or durability certification. This is a release acceptance blocker until tested in an isolated Supabase environment.
- Protective exits are simulated market closes at the next observed fresh quote with costs; they are not exchange-native stop/limit orders. Touches between samples or while Render sleeps/restarts/network/database is unavailable can be missed. On restart only current fresh observed price is used; no retroactive/artificial fill is invented. Practice needs an awake web process; a sleeping free instance cannot guarantee monitoring. Do not disable the flag or stop the service with an open practice position without understanding this limitation.
- Slippage and fees are fixed existing-engine assumptions, not a measured bid/ask/depth execution guarantee. SHORT is virtual; no assets are borrowed and no funding/borrow charges are modeled. A large adverse gap can exceed the planned risk. Existing engine losses are recorded honestly without clipping: ledger balance can become negative, available spendable balance is floored at zero and new entries are blocked. No negative available cash or fictitious replenishment is shown.
- UI chart contains observed quote points during the page session, not invented historical candles. Existing terminal charts/positions are not altered. Current PnL is hidden when the saved mark is stale or monitoring failed; saved ledger values remain explicitly last known.
- Continuous UPDATE records consume database/storage/request quotas. Watch Supabase limits and event growth; no automatic destructive retention/reset is included. No new paid resource or service was provisioned. Exact cost depends on the owner's existing Supabase/Render plans and was not inspected.

## Verification performed

A read-only probe of the real Binance public quote endpoint also passed from the local environment (see `PAPER_PRACTICE_PUBLIC_QUOTE_PROBE.json`); no trade or database operation used that probe. It does not verify Render network availability.

Full Python suite: **1,231 passed**, one existing deprecation warning. All **17 JavaScript suites passed**, including Practice retry/validation/chart/path-scope behavior. All **33 focused Practice checks passed**. See `PAPER_PRACTICE_TEST_RESULTS.json` for commands/counts/versions and `PAPER_PRACTICE_BROWSER_VERIFICATION.json` for actual Chromium evidence. All quotes and RPC writes in these tests are explicitly OFFLINE fixtures, never production market substitutions.

Coverage includes LONG/SHORT, manual/TP/SL closes, exact independent Decimal fee/PnL checks, auto-sizing limits/available cash, already-crossed/raw-quote stop rejection, missing/stale/future/regressing quotes, quote-source allowlist, one-position cap, concurrent attempts, duplicate ticks/requests, restart recovery, lost OPEN/CLOSE acknowledgements, changed-body UUID conflicts, DB failure/recovery, auth/CSRF/schema checks, disabled-mode isolation, scope restrictions and insolvency behavior.

Real local Chromium exercises the actual page, local HTTP API, unchanged execution functions, mock RPC receipt confirmation, chart, OPEN → UPDATE → manual CLOSE and an identical state after server restart. Its fixture server is guarded OFFLINE-only, temporary, and not mounted in `app.main`. No public test-price or synthetic-signal endpoint is added. This is never LIVE VERIFIED or real Supabase proof.

Code review and a separate security review inspected transitions, fee/PnL accounting, quote freshness, raw/slipped stop validation, namespace isolation, SQL row-lock/CAS/idempotency, uncertainty/read-back behavior, server-only credentials, fixed GET/RPC allowlists, owner/CSRF and textContent rendering. Review fixes included preserving pending commands on corrupt database responses (503 rather than a definitive client error), exact raw-quote stop guards recovery of a transient monitor error, definitive 422 validation handling, and a strict frontend request-path allowlist so a tampered saved retry cannot target another portfolio. No production engine, strategy, risk parameters or Aura scheduler files changed. Remaining unverified PostgreSQL/Render behavior blocks a readiness claim.

## Safe future deployment — owner action only

1. Review this standalone main-based Draft PR and SQL. Do not merge any Research Lab PR for this feature. Arrange deployment/Auto Deploy controls so a merge cannot start an unapproved rollout.
2. In a separate isolated Supabase environment first, inspect/apply `scripts/practice_schema.sql` and verify RPC grants/RLS, atomicity, duplicate UUID and stale revision behavior. `pgcrypto` must be available in schema `extensions`. Do not test against existing Auto42 tables or import production positions.
3. Once authorized, apply the reviewed additive SQL to the chosen PRACTICE project. Retain database backups. No reset, existing-table migration or production ledger edit is required.
4. Configure only on the server:

```text
AURA_PRACTICE_ENABLED=false
AURA_PRACTICE_SUPABASE_URL=https://PROJECT.supabase.co
AURA_PRACTICE_SUPABASE_SERVICE_KEY=<server-side service role key>
AURA_TESTNET_VIEW_PASSWORD=<strong owner password, at least 12 characters>
```

The dedicated URL/key never fall back to AURA_AUTO42_* credentials. Do not copy secrets into Git, screenshots, URLs or browser storage. Existing Aura 4.2 settings/secrets remain unchanged.

5. Only after explicit merge/deploy approval, deploy the reviewed commit using the existing `python start_web.py` entry point (one worker). Check normal terminal health, Aura scheduler ticks and existing positions first. Any deploy restarts the shared application; existing restart protections still apply.
6. Explicitly set `AURA_PRACTICE_ENABLED=true` after SQL/config review and restart as required by Render. Check owner-only `/api/practice/state` gives the separate fresh initial 10,000 balance, scope and a verified save revision. Verify `/api/practice/quote` is actually fresh from Binance on that Render region. If either request fails, do not attempt an entry.
7. Monitor worker uptime, database errors and sampling gaps. Do not claim live success merely from a green health endpoint or an offline test report. Rollback by disabling the PRACTICE flag/feature after closing practice exposure; preserve its tables/history and never reset Auto42.

## First real practice transaction and durable proof

1. Open `/api/practice/login`, authenticate as owner, press Connect. Confirm PAPER PRACTICE, a fresh UTC quote, separate balance and `SUPABASE_PRACTICE_ONLY` storage. Main Aura balance/positions must remain unchanged.
2. Enter explicit sensible SL and TP on the correct side of the current price; allow for costs. Choose OPEN LONG or OPEN SHORT. Size is automatically risk-limited. Do not send a new request if the result is uncertain: use **Repeat unconfirmed request**, preserving the UUID.
3. Verify a receipt ID, an OPEN journal entry, position ID, Entry/SL/TP chart lines, size and fee, plus a new database revision. A UI-only visual position is not enough. Close the browser briefly and reopen to check UPDATE events continued while the process stayed awake.
4. Press CLOSE POSITION; verify the same position ID has CLOSE, fees/net PnL and no open position. For SL/TP tests wait for genuine market movement; never inject a fake production quote. Use small risk-limited practice exposure and expect sampling gaps.
5. Verify directly in the Supabase SQL editor (owner access), substituting only the PRACTICE IDs:

```sql
select revision, saved_at,
       payload::jsonb->>'practice_scope' as scope,
       payload::jsonb->>'balance' as balance,
       payload::jsonb->'position' as position,
       sha256 = encode(extensions.digest(convert_to(payload,'UTF8'),'sha256'),'hex') as checksum_ok
from public.aura_practice_account where id=1;

select seq, id, kind, created_at, ingested_at,
       payload::jsonb->>'command_id' as command_id,
       coalesce(payload::jsonb->'payload'->>'id',
                payload::jsonb->'payload'->'position'->>'id') as position_id,
       payload::jsonb->'payload'->>'exit_reason' as close_reason,
       payload::jsonb->'payload'->>'realized_pnl' as net_pnl,
       sha256 = encode(extensions.digest(convert_to(payload,'UTF8'),'sha256'),'hex') as checksum_ok
from public.aura_practice_events order by seq desc limit 100;
```

For an older position, select its OPEN/CLOSE explicitly rather than relying on the latest 100 updates:

```sql
select seq, id, kind, payload::jsonb->'payload' as trade,
       sha256 = encode(extensions.digest(convert_to(payload,'UTF8'),'sha256'),'hex') as checksum_ok
from public.aura_practice_events
where kind in ('OPEN','CLOSE')
  and payload::jsonb->'payload'->>'id' = 'PRACTICE_POSITION_ID_FROM_RECEIPT'
order by seq;
```

6. Match OPEN and CLOSE position IDs/UUIDs with browser receipts; both checksums must be true and CLOSE must contain the observed exit/fees/PnL. Retry a completed UUID and verify no second OPEN/CLOSE or fee is added. Restart Render only with permission and check the same saved state/revision/history; do a separate open-position restart test to verify protective recovery without duplication. Do not edit the existing Aura portfolio as part of these checks.

Only recorded results from that actual Render/Supabase cycle can change the verification status. No real exchange order is ever required.

## Local reproducibility

```sh
python -m pytest -q
node tests/test_practice_frontend.cjs
python -m scripts.verify_practice_offline --output /tmp/practice-offline-NEW.json
```

The last command requires installed Chromium and a new output path; it explicitly uses fake quotes and an SQLite-backed mock RPC, creates only temporary local resources and refuses Render. Managed-cloud test wakeup accommodations remain in test tooling, not production event-loop code. No dependency change or paid API is needed for normal Practice operation.

# PAPER PRACTICE — REAL POSTGRESQL VERIFICATION

Scope: existing Draft PR #12 only; local PostgreSQL 16.15 in a disposable Docker
container, network=none, no published ports, no production credentials. The test
database includes the actual main Auto42 schema and a separate offline account,
so isolation is checked against real existing tables/functions, not empty names.
No production Supabase or Render operation was performed.

| Status | Value | Evidence |
|---|---|---|
| POSTGRESQL_VERIFIED | TRUE | Actual migration and reapplication succeeded; 2 tables, 3 RPCs and trigger function created; transactions, CAS, quote age and restarts exercised. |
| RLS_VERIFIED | TRUE | Actual anon/authenticated table/RPC/sequence attempts denied. Temporary table grants in the test DB still yield zero visible/updated rows and INSERT RLS rejection. Non-superuser service_role successfully calls SECURITY DEFINER RPCs while direct ledger writes are denied. |
| OPEN_CLOSE_VERIFIED | TRUE | Six actual PostgreSQL OPEN → UPDATE → CLOSE cycles: LONG/SHORT × manual/TP/SL. Existing Service, Store validation and engine; independent Decimal fee/slippage/PnL checks. |
| PRODUCTION_READY | FALSE | Hosted PostgREST/JWT/configuration, Render connectivity and the actual live-price Render → Supabase cycle remain unverified. |

Machine-readable evidence, all 23 named checks, six full cashflows, image digest,
SQL SHA256 and matching before/after Auto42 hashes:
[PAPER_PRACTICE_POSTGRESQL_VERIFICATION.json](PAPER_PRACTICE_POSTGRESQL_VERIFICATION.json).
The accompanying `PAPER_PRACTICE_POSTGRESQL_REGRESSION_RESULTS.json` records the
full Python/JavaScript rerun and source identities.

## Verified correction

With Supabase-like broad default grants, the previous SQL revoked table rights
from anon/authenticated but not the new identity sequence. The real PostgreSQL
regression failed with `anon: inherited sequence grant remains`. Default table
grants also let service_role write directly, bypassing RPC validation.

The correction revokes direct rights on the two practice tables **and their
sequence** from PUBLIC, anon, authenticated and service_role. Only the three
intended SECURITY DEFINER RPCs are granted to service_role. This changes no
Auto42, Paper Engine, strategy, scheduler or Research Lab file and no existing
trading table. Default privileges for other/future tables are not modified by
the migration. The broad default-privilege setup exists only in the local test.

Tests verify actual failed nextval/direct UPDATE calls, not only SQL text.
Other checks include a bad second event rolling back the first INSERT, an
injected account UPDATE failure rolling back OPEN/fees, recovery with the same
UUID, independent concurrent OPEN and CLOSE transactions, duplicate receipt
binding, an open account surviving SQL reapplication, and actual PostgreSQL
restarts both before and after CLOSE. An Auto42 dump/schema/function checksum
is identical before and after the complete run.

## Boundaries and review

There is **no mocked database** in this verification. A local psql adapter calls
the actual RPC functions, reusing the production Service and Store validation;
it replaces only the HTTP wire transport. Consequently this is not a hosted
Supabase/PostgREST authentication or HTTP-contract certification. Existing
offline HTTP/auth/CSRF tests cover application behavior separately. Test quotes
are fixed offline fixtures, not real BTCUSDT market observations or strategy
profitability evidence. Sampled stop gaps can exceed planned risk; losses are
recorded honestly. This never sets LIVE AUTONOMOUS EXECUTION to VERIFIED.

Code review: migration diff is limited to practice object ACLs; existing engine,
policy and persistence schemas outside practice are unchanged. Runtime does not
import the test runner. Transactions still lock and commit state/events together.

Security review: role/sequence default grants corrected, SECURITY DEFINER RPCs
retain explicit search paths, owner/CSRF code unchanged. The runner refuses
Render, selects only the local Docker socket, has no DSN/URL input, uses a unique
labelled networkless container/test DB, and removes its own test volume. No key
is read, emitted or committed. Residual release blockers are the untested hosted
gateway/Render cycle and shared Free-tier quota/uptime limitations, rather than
an unresolved failure in these local PostgreSQL checks.

## Owner instructions

Use [PAPER_PRACTICE_SUPABASE_DEPLOY_RU.md](PAPER_PRACTICE_SUPABASE_DEPLOY_RU.md)
for the exact existing-Supabase-Free preflight, whole-file migration, RPC/RLS
verification, dedicated Render variables, first LONG, manual CLOSE, SQL receipt
proof and safe disable sequence. No new paid project is required; shared quotas
and service-role credential privileges remain shared. Do not merge or deploy
without the owner's separate authorization.

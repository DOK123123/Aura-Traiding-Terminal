# Cloudflare → Render → Supabase: evidence of a saved scheduler tick

Status of the investigated production invocations: **NOT VERIFIED**.
24 October 2026 06:22 and 06:27 GMT+3 mean **03:22 and 03:27 UTC**.
Only the owner's reported `scheduled / outcome=ok` is available. No authorized
Cloudflare invocation logs, Render logs or Supabase receipts were accessible.
Public health returned 200; owner status/readiness returned 401. No attempts to
bypass authorization, execute ticks, initialize, control PAPER or write SQL were
made. Production SHA supplied by the owner: 1f885bfd4c465aacead19b88b98526e177db4607.

## Confirmed gaps, not guessed production causes

The deployed source already logs REQUEST_STARTED, RENDER_REACHED (HTTP status),
REQUEST_FAILED and TICK_SAVED. But it did not return or log the saved TICK ID,
creation time or creating deployment SHA. Ordinary successful OFF ticks also
had no structured server delivery log. Consequently the logs could not join a
specific invocation to its immutable database receipt.

`outcome=ok` means the scheduled JavaScript handler completed normally. In this
source it can mean DISABLED without an HTTP call, diagnostics PASS/BLOCKED without
a tick, or a completed guarded tick. It alone proves neither Render delivery
nor Supabase persistence. Network/auth/contract failures are rethrown because
scheduled() awaits run(); this is not converted to success.

Why the owner saw no application logs cannot be determined without deployed
code/bindings/observability settings. Do not assert that cron was disabled,
operation was diagnostics, the secret was wrong or Supabase failed. These are
distinct branches to distinguish using the actual application events.

**Name mismatch:** owner named `aura-ctive43-scheduler`; repository config names
`aura-active43-bitget-free-scheduler`. Do not silently correct the spelling or
deploy a new Worker. Verify the existing Dashboard resource before any approved
deployment. The repository name/default bindings do not prove production values.

## Changes

- Worker emits a random per-invocation **application correlation ID**, UTC,
  scheduled UTC, duration_ms, operation, attempt and HTTP status. This ID is not
  a claimed Cloudflare platform invocation ID or a trade idempotency key. The
  platform's own invocation ID can be recorded separately in Cloudflare Logs.
- The same `X-Aura-Invocation-Id` is used on retries. Render validates it after
  existing scheduler authentication and logs safe ACTIVE43_TICK_DELIVERY events.
  Missing correlation headers remain compatible with existing GitHub clients.
- Render returns tick_id, tick_created_at, tick_slot_start and
  tick_receipt_verified **from Store.lookup() read-back**, not a fabricated ID.
  A missing/corrupt receipt cannot report a successful save.
- Each new TICK receipt includes the sanitized current Render commit in its
  existing payload. The response separates current render_commit from the
  receipt's original tick_render_commit. Old duplicate receipts remain old;
  no transaction or history entry is rewritten.
- Worker requires valid receipt evidence before TICK_SAVED. An old backend that
  returns only state_saved yields TICK_RECEIPT_UNAVAILABLE, never fake success.
- Exhausted/rejected tick delivery produces terminal TICK_FAILED in addition to
  the existing per-attempt REQUEST_FAILED. A persisted PAUSED receipt can be
  logged as saved, but ends in TICK_FAILED and remains an exception, not readiness.
  Valid BLOCKED diagnostics remain DIAGNOSTICS_BLOCKED, not delivery failure.
- Explicit logging sampling=1 is prepared in repository config. Cron defaults
  remain disabled/diagnostics; no production binding or schedule is changed.

No new endpoint, account, service, secret, schema/migration, risk setting,
strategy, balance or order mechanism. Existing atomic commit/idempotency remain
unchanged. Application receipt metadata is additive to the existing JSON/RPC.
No private Bitget API calls exist in this change.

## Timeouts, retry and duplicate semantics

Fixed destination remains the existing Render host: off_only calls
/api/active43/verify-off-tick, saved_mode calls /api/active43/tick and diagnostics
calls the read-only /api/active43/diagnostics/scheduler. Existing independent
scheduler auth stays required; redirects are rejected.

At most two Worker attempts, normally 120s each, within the existing four-minute
budget (also bounded by scheduled time). Stale/future triggers are rejected.
401/403 and permanent server/configuration failures do not retry. 429 honors
Retry-After; 502/503/504 and Render loading HTML wait for cold start before a
bounded retry. No excessive/date-based cooldown is bypassed. Aborts distinguish
request and body phases. Failed JSON, source/PAPER contracts and missing receipt
metadata are not success. Render itself retains its 50s tick budget.

The server's existing epoch/five-minute-slot key, CAS and immutable TICK receipt
are the idempotency authority. The application invocation ID does not replace
them. Repeated deliveries can have different invocation IDs but the same tick
ID. These are one saved cycle, not two. No extra account writes are introduced
by logging or duplicate response formatting.

## Approved rollout procedure — NOT performed by Codex

Both **Render and Worker code deployment are required** for complete receipt
evidence. No SQL, new keys or service creation is needed.

1. Keep PAPER OFF. After review/merge and separate owner approval, manually
   deploy the new backend to the existing Render service. Record actual Live
   commit SHA and completion UTC. The old Worker accepts additive response fields.
2. Update only code of the **existing** intended Worker in Cloudflare Dashboard
   using worker.mjs. Preserve its existing secret/bindings/cron and do not use an
   unmodified default-name deployment that would create another Worker. Check
   Logs/Observability application logs enabled and 100% sampling for this test;
   platform logs/filters, retention and quotas can still affect visibility.
   This document does not authorize enabling a disabled cron or switching PAPER.
3. In Workers & Pages → existing Worker → Logs/Observability, use UTC and include
   application console events, not only `cf-worker-event`. Wait for **automatic
   scheduled** invocations. Do not use Run/Test/manual HTTP as automatic proof.

If Worker is deployed first, TICK_RECEIPT_UNAVAILABLE is a useful deployment
mismatch diagnosis, not a reason to loosen validation or claim success.

## Exact acceptance test for two automatic OFF cycles

Filter component=ACTIVE43_FREE_SCHEDULER and
worker_version=ACTIVE43_CF_RECEIPTS_2026_10_24. For two scheduled invocations after
the backend's actual Live time, record:

| Field | Required |
| --- | --- |
| invocation_id, platform invocation ID | Application ID present; record platform ID separately |
| UTC start/end, scheduled_time, duration_ms | REQUEST_STARTED through terminal receipt; distinct planned slots |
| operation | off_only or saved_mode; diagnostics does not count |
| HTTP | RENDER_REACHED / final receipt HTTP 200 |
| result | TICK_SAVED, status=COMPLETED, mode=OFF, opened=0, closed=0 |
| persistence | state_saved=true, tick_receipt_verified=true, actual tick_id |
| uniqueness | Two **different tick_id and tick_slot_start** values, ideally 300s apart |
| creating version/time | tick_created_at after Live; tick_render_commit matches the intended backend SHA |
| errors/retries | Record each attempt; no terminal TICK_FAILED for an accepted cycle |

Look up the exact returned IDs read-only in the existing
`aura_active43_bitget_events`: kind=TICK, matching created_at and payload
render_commit. Compare the existing owner read-only snapshot/financial history:
OFF, 10000 USDT, no position or pending, unchanged realized PnL/OPEN/CLOSE history.
TICK audit entries are expected to be added. No artificial signal or trade is
needed. A duplicate old slot or old pre-deploy receipt does not satisfy this test.

Only these real logs/read-backs can change status to VERIFIED. Local/CI fixtures,
HTTP 200 alone, outcome=ok, two diagnostics or two retries of one ID cannot.
PAPER ON requires a separate later authorization; OFF ticks do not validate
profitability or natural production OPEN → CLOSE.

## Verification scope

Regression tests cover receipt-based success, legacy/malformed receipt rejection,
401/403/429/5xx, request/body timeout, stable retry correlation, duplicate IDs,
distinct five-minute slots, blocked decisions, secret redaction and passive
logging failures. Existing real-PostgreSQL/Worker integration tests now also
check returned IDs against logs, duplicate-vs-new slots and restart recovery.
They run only in the isolated regression CI. See its actual run for results;
none of those synthetic fixtures are production scheduler verification.

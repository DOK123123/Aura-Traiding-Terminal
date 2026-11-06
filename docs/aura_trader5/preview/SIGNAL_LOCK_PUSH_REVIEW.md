# PR #83 review evidence

## Code review

Reviewed observer/lifecycle/quotes, private storage/RPC, UI and sender separately.
No changes to strategy conditions/weights, trading permissions, account clients,
wallet SQL, PAPER, Active43, frozen research baseline or production entrypoint.
The existing Python explanation output gains structural pivot metadata only.
The runtime integration manifest updates reviewed Preview main/page digests;
archived research digests and reproducibility assertions remain enforced.

Checked: immutable IDs, monotonic CAS version, terminal non-resurrection,
WATCH plan immutability, missing checks and freshness, original deadline,
restart UNKNOWN, replaced structure/locked SL/TP breach, paged restart reads,
preservation of manual selection (including older records) and card DOM.
During review, fixed missing-condition reporting, restored-selection validation,
persisted selection/pin state and CANDIDATE Push threshold at claim time.

## Security review

Traced owner Basic Auth: existing middleware protects new GET/POST/SW routes.
Push mutations separately enforce Origin, custom header, bounded JSON, valid
P-256 subscription keys and a fixed FCM HTTPS endpoint allowlist. No wildcard
CORS or arbitrary notification/navigation URL. New Requests sessions contain no
Preview Basic credentials. TLS stays enabled; redirects stay disabled.

Supabase uses only the already bound Preview host/key and existing scope guard.
Private tables/RPC grant access only to service_role with RLS and no browser SQL
policies. Config excludes private key and subscriber material. Sender exception
text and endpoints are never logged; outbox response to the owner contains only
status/kind/code/time. Subscription removal/410 clears endpoint/key material.
Root Service Worker has no fetch/cache handler, stores no owner password and
executes no trading commands. The VAPID generator is owner-run, exclusive 0600,
outside the repository, never executed by the application.

Residual limits: Chrome Android FCM only; no real handset receipt evidence;
no guarantee of sound/delivery; missing VAPID prevents sending. At-most-once
claims deliberately trade retries for no duplicate alerts: uncertain sends remain
UNKNOWN_SEND_OUTCOME. A provider acceptance is not a device delivery receipt.
Render Free cannot observe/send while sleeping. Private state has bounded capacity
and a fail-closed limit; future archival must retain deduplication identities.
INFO `rls_enabled_no_policy` is expected for service-role-only tables; it is not
resolved by granting browser policies. No unresolved critical/high finding was
identified in these review passes; CI/release/handset gates remain separate.

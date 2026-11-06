# Aura 5 Signal Lock / Android Push — implementation status

This branch is a **foundation only, not a release**. No production or Preview
runtime imports the reducer yet. Do not merge/deploy it as the requested feature.
`NO_EDGE_FOUND` remains mandatory.

## Implemented in isolation

`app/manual_preview/lifecycle.py` is a pure deterministic reducer:

- structural SHA-256 identity excludes score, quote price and tick timestamps;
- admission at 70, score retention down to 65 (not a win probability);
- mandatory checks/geometry are independent of score;
- CANDIDATE → WATCH and INVALIDATED / EXPIRED / UNKNOWN transition events;
- immediate terminal UNKNOWN on untrusted data, with no current plan;
- fixed first detection, initial evidence and WATCH plan;
- deterministic event IDs and no repeated events for unchanged state.

The caller must supply validated structural anchors and trustworthy market
freshness, explicitly invalidate a crossed locked structural/SL/TP level, and
atomically persist the returned record/event with an outbox. A pure reducer does
not establish any of those integration guarantees. Recovery from UNKNOWN cannot
reactivate the same episode: a new structural identity is required.

Tests are synthetic, local, and never injected into deployed market history.
The JSON roundtrip test verifies serialization, **not durable Supabase storage**.

## Confirmed release gaps

- The existing observer still stores its journal on ephemeral Render storage.
- The existing cards still use client freshness/selection, not this reducer.
- There is no durable signal/subscriber/transition/delivery-outbox schema yet.
- No Service Worker, Push API subscription flow or VAPID sender is implemented
  by this foundation.
- No real Android delivery is verified.
- The new reducer must not be advertised as deployed server Signal Lock.

## Owner preparation for VAPID (dependent stage only)

The current cloud executor has no `AURA_PREVIEW_VAPID_PRIVATE_KEY`,
`AURA_PREVIEW_VAPID_PUBLIC_KEY`, or `AURA_PREVIEW_VAPID_SUBJECT` bindings. This
check does not establish whether those names exist in Render; secret values were
not retrieved from Render.

Before activating a future sender, the owner should generate a P-256 VAPID key
pair using a reviewed Web Push/VAPID tool in a trusted environment. Store the
private key only as `AURA_PREVIEW_VAPID_PRIVATE_KEY` in the isolated Render
service `srv-dbh1vljl550s738f4t30`. Never paste it in a PR, chat, URL or browser.
Store the matching URL-safe public application-server key as
`AURA_PREVIEW_VAPID_PUBLIC_KEY`; only this key may reach the browser. Configure
`AURA_PREVIEW_VAPID_SUBJECT` as an owner-controlled `mailto:` or HTTPS contact.
Do not reuse production keys or rotate an existing pair without reconciling
subscriptions. Do not enable a sender until implementation/security tests pass.

Subscriptions contain sensitive endpoint/capability URLs and keys. Keep them
server-side in the isolated Preview database, RLS enabled, no anonymous or
browser SQL access. Use same-origin owner-authenticated, CSRF-protected,
bounded subscription/settings/test endpoints. Never accept arbitrary push
endpoint hosts: a sender needs reviewed provider host allowlists, redirect/TLS
verification, DNS/private-address protection, payload limits and bounded retries.

A push-service 2xx means accepted by provider, not delivered to Android. Record
`ACCEPTED_BY_PUSH_SERVICE`, never `DELIVERED`, unless a distinct client receipt
exists. Expired 404/410 subscriptions must be retired, 429 must respect retry
limits; an uncertain send outcome must not be presented as successful delivery.

## Work required before release

1. Review/apply an isolated Supabase schema with scope guard, atomic CAS,
   transition journal, subscriptions and unique event/subscription outbox keys.
2. Integrate a server-owned reducer loop independent of browser requests, with
   fresh quotes and existing closed-candle/structure validation. Never widen the
   5-second freshness contract to hide observer delays.
3. Replace automatic card selection with stable manual selection, event badge,
   restored disclosure/scroll state and server-status expiry guards.
4. Add root-scope Service Worker and subscription/preferences/test UI; WATCH
   default, CANDIDATE opt-in. Notification URLs select a validated scenario ID.
5. Verify restart durability, races/idempotency and notification retries; run
   exact-head Python/JS CI, desktop/412px browser fixture tests (500 ticks), and
   real Android foreground/background delivery separately from mocked tests.
6. Audit, merge into `feature/aura-live-manual-trader5`, deploy only the existing
   isolated service, then verify deployed head, health, logs and live UI.

Render service inspection confirmed plan `free`, one instance, auto-deploy off.
While it sleeps there is no running observer/sender, so it cannot discover or
send timely new signals. On wake, a worker must reject stale events and reconcile
storage. A successful point-in-time health check is not continuous observation.
Android/browser battery restrictions and push-provider queues also preclude a
guaranteed delivery promise. No keepalive loop or paid resource is authorized
by this document.

# Signal Lock and Web Push — implementation stage, NOT RELEASED

This draft adds reviewable, offline-tested components. It does **not** activate
Signal Lock or push on the deployed terminal. Existing runtime routes, observer,
manual trading controls, PAPER, Active43 and production stay unchanged.

## Implemented components

- Pure lifecycle over existing explainable evidence: CANDIDATE at 70+, WATCH
  requires every condition and the existing fee/slippage/funding risk calculation.
  Candidate exit hysteresis is 65; this does not alter the strategy's WATCH gates.
- Identity includes model, strategy, direction, timeframe and closed-candle cutoff;
  score/quote changes do not create events. Terminal events cannot rearm.
- Data loss becomes UNKNOWN immediately on observation; read-time projection also
  suppresses a persisted WATCH after five seconds, restart, expiry or clock rollback.
  Archived plans are historical only. Crossing the archived SL/TP invalidates it.
- Event and notification intents commit together through a versioned CAS store.
  One intent per event/status and a five-minute stream cooldown. These are **not**
  sent notification receipts. Capacity fails closed at 2,000 events / 4 MB;
  archival/retention must be designed before continuous operation.
- Separate-schema SQL proposal, service-role-only RPCs, RLS and Preview scope
  guard. No hosted migration was applied. No existing ledger table/guard changes.
- Optional push transport validates subscription keys and allowlisted HTTPS push
  hosts, disables redirects, bounds timeout/size, sanitizes errors and distinguishes
  HTTP acceptance, expired subscription and retry. No keys are generated and
  optional pywebpush/requests dependencies are not installed or activated.
- Service Worker validates notification payloads, labels expired messages and
  opens only an own-origin event URL. It is not registered in the live app.
- Standalone mobile view preserves the reading selection, TF/details preferences
  and scroll while quote text changes independently; history/status filters and
  explicit new-event selection. It is not mounted in the live Signals tab.

## Verification scope

Python lifecycle tests cover 500 fresh timestamp updates, promotion, stale data,
expiry/invalidation, malformed plans, CAS conflicts and a disposable restart.
The CI PostgreSQL test applies the proposed SQL **only** inside a disposable
network=none Docker database and checks roles, CAS, restart, scope refusal and
unchanged existing Preview guard/ledger. Frontend tests use a synthetic push
event: they cannot establish OS notification delivery. Chromium tests exercise
the standalone view on desktop and 432/360 px Android emulation with 500 quote
updates per viewport and no non-GET requests.

## Release blockers and work remaining

The user's explicit stop condition applies: activation requires owner-provided
VAPID configuration and an approved change to the existing dedicated Preview DB.
Do not invent keys, retrieve credentials into development, apply this SQL or
merge/deploy this draft as a complete feature.

After that gate, still required:

1. Review and pin actual Web Push dependencies; provide VAPID configuration only
   through the existing service's secret environment controls.
2. Apply/review the schema on the attested Preview project, integrate the observer
   with the durable store in a worker thread, mount UI and expose owner-authenticated
   read-only event APIs. No fallback to Render's ephemeral SQLite.
3. Implement durable subscription/preferences storage, owner/CSRF-protected
   subscribe/unsubscribe/test routes, delivery claims/retries and expired
   subscription cleanup; integrate notification click with the actual view.
   Current intents alone do not guarantee exactly-once external delivery.
4. Choose an existing permitted background scheduler and review capacity. The
   existing Free Render web service sleeps after 15 minutes without incoming
   traffic, and its local filesystem is ephemeral. A sleeping service cannot
   detect new signals. No always-on or round-the-clock delivery claim is valid.
   No worker, paid service or keep-alive workaround is provisioned here.
5. Run end-to-end subscription/permission/error tests, real push delivery on an
   owner's Android with browser closed/screen locked, full CI and hosted mobile
   tests before release. Sound depends on Android/browser settings, DND and power
   restrictions; HTTP push acceptance is not device delivery.

References: https://render.com/docs/free and
https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe

Current status: lifecycle/component tests possible; live event creation **OFF**;
real Web Push **NOT CONFIGURED**; real POCO F7/locked-screen delivery **UNKNOWN**;
merge/deploy **BLOCKED**, published service unchanged.

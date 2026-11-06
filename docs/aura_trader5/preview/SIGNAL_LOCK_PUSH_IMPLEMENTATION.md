# Aura 5 Signal Lock and Android Web Push (PR #83)

Only the isolated Preview service `srv-dbh1vljl550s738f4t30`, branch
`feature/aura-live-manual-trader5`, and Supabase Preview project
`kkxdftdojvnsjqlrulpb` are in scope. `NO_EDGE_FOUND` is preserved. No execution
or account changes are introduced.

## Server-owned episodes

`signal_service.py` runs independently of open tabs. It evaluates the existing
closed-candle strategies and a separately refreshed, validated public Bitget
quote. The five-second freshness limit is unchanged. Scores are technical
condition counts, not win probabilities.

Identity uses strategy, direction, timeframe, model and confirmed pivot timestamps;
it excludes score, quote price, rolling array indices and tick timestamps.
Admission is >=70; a retained CANDIDATE can fluctuate down to 65. This hysteresis
never relaxes mandatory WATCH checks, geometry, Net R/R, freshness or expiry.
The original WATCH plan and first detection remain fixed. Breached original
SL/TP, lost mandatory checks or changed structure retire the episode. These
are signal statuses, never virtual or real orders. EXPIRED covers the original
entry deadline; UNKNOWN immediately suppresses an untrusted/unobserved episode.
A terminal episode cannot silently reactivate; a new structure is required.

On process restart, durable history is restored; any previously active episode
becomes UNKNOWN because the intervening market path was not observed. Browser
reads are side-effect-free and independently fail closed when the cached view or
quote ages. Selection, disclosure DOM and scroll are not replaced each tick;
new events produce a badge and manual scenario choices. History includes all
transition statuses. Public UI shows the most recent 200 records; the database
retains permanent identities/events with a 5,000-record safety cap. Hitting a
storage/payload cap fails closed and requires an explicit retention design,
never deleting watermarks and silently re-notifying old episodes.

## Storage and isolation

`scripts/sql/aura5_signal_lock.sql` refuses any project without the exact Preview
scope marker. New tables are in private `aura5_signals`, preserving the existing
wallet guard/public table allowlist. RLS is enabled; `anon` and `authenticated`
have no schema/table/function access. The SECURITY INVOKER RPC requires the
existing isolation guard and service_role. No wallet RPC or wallet data is used.

Atomic CAS commits records and transition events with a unique event ID.
Outbox entries are unique per transition/subscription. Subscriptions (maximum 32)
contain sensitive capability endpoints/keys, remain server-only, and are never
returned by config/history. Scope is re-attested before every RPC. Restart tests
use disposable local PostgreSQL, not hosted synthetic market data.

## Push semantics

WATCH is the default. CANDIDATE is a separate explicit preference. Supported
provider: Chrome Android FCM, fixed HTTPS host and path allowlist. Owner Basic
Auth stays on the Preview origin. Subscription/settings/test endpoints require
same-origin Origin plus a custom CSRF header and bounded JSON. The root-scope
Service Worker has no fetch/cache handler and never stores owner credentials.
Notification clicks open a same-origin scenario ID; no external URLs or orders.

The sender validates matching P-256 VAPID keys, preserves TLS verification and
proxy settings, rejects redirects, and uses an 8-second timeout and 60-second TTL.
Pending items older than two minutes, stale episodes and inactive subscriptions
are skipped. A claim is durable before sending. To prioritize no duplicate
alerts, uncertain sends are not retried blindly: abandoned claims become
UNKNOWN_SEND_OUTCOME. 404/410 retires and clears the subscription. Other provider
errors are journaled without unbounded retries. Test sends are limited to one
per minute/subscription. The user can inspect the latest 30 attempts.

`ACCEPTED_BY_PUSH_SERVICE` means provider acceptance, **not receipt by Android**.
No handset delivery acknowledgement is implemented. System notifications request
sound (`silent:false`); Android user settings, battery/Doze restrictions and
provider behavior govern actual visibility/sound. Permission denied and missing
browser APIs are reported; expired subscriptions require user re-enablement.

## Owner-only VAPID setup

The executor presence check found none of:

- `AURA_PREVIEW_VAPID_PRIVATE_KEY`
- `AURA_PREVIEW_VAPID_PUBLIC_KEY`
- `AURA_PREVIEW_VAPID_SUBJECT`

That does not establish Render's settings: the connected Render tools can update
variables but cannot list their names. Never retrieve or paste secret values to
prove readiness. After deployment, authenticated `GET /api/preview/push/config`
reports name-presence booleans and validates the pair; only the public key is
returned. An invalid/missing pair disables the sender, not Signal Lock.

If no Preview key pair exists, on an owner-controlled trusted computer with the
pinned requirements installed, run:

```sh
python scripts/generate_preview_vapid.py --output /secure/private/aura5-preview-vapid.json --subject mailto:YOUR_OWNER_CONTACT
```

Use an existing private directory outside the repository. The command refuses
overwrite, creates mode 0600, and does not print key values. Replace the contact
with a real owner-controlled address. Do not run this on an untrusted/shared
machine. Do not generate a new pair if subscriptions already use an existing one.

In Render Dashboard, select **only** service `srv-dbh1vljl550s738f4t30` in
workspace `tea-db5t6g8473hc73cb2t0g`. Copy the three fields directly from that
private file into Environment. Keep PRIVATE_KEY secret and never place it in
GitHub, chat, frontend code, URLs, screenshots or logs. Do not copy Supabase
service keys into the browser. Securely retain the VAPID pair for future deploys;
rotating it requires re-subscribing devices. Confirm only that the three names
are configured. No new paid resource is needed.

After release on Android Chrome, open the authenticated Preview → Signals →
Android Web Push → Enable. Grant permission, leave CANDIDATE unchecked for
WATCH-only. Send Test; distinguish queued, provider acceptance and actual phone
receipt. Repeat with browser minimized. Record the real phone/Chrome version,
permission and observed receipt separately from Chromium fixtures.

## Render Free and release gate

No worker runs while Render Free sleeps. Signals during sleep cannot be detected
or sent in real time; a restart creates an explicitly unobserved gap. No keepalive,
paid plan, external scheduler or extra service is added. A health check is only a
point-in-time observation. Android delivery is not guaranteed even with a running
server.

Merge/deploy requires exact-head Python/JS/PostgreSQL and Chromium checks, review,
Preview-only schema verification, and owner confirmation of required VAPID setup.
Never claim the feature is deployed or handset delivery verified solely from the
offline tests. Only deploy the existing isolated service. Production, PAPER,
Active43 and real/virtual trades remain out of scope.

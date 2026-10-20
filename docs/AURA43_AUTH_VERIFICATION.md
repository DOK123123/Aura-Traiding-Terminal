# Aura 4.3 Bitget: HTTP 401, verification 2026-10-20

## Proven result, not a guess about secret values

Run [#5 / 39377928524](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39377928524)
executed main `d1faf1ee96ddc4c07d80079750258649f591acf6` and reported only HTTP 401.
The secret was available to its job (masked by GitHub).

Read-only diagnostic [#6 / 39378543713](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/runs/39378543713)
ran from this branch. Its safe evidence:

```json
{"token_present":true,"token_format_valid":true,"token_has_outer_whitespace":false,
 "header_attached":true,"origin_header_present":false,"method":"POST"}
```

Response: **HTTP 401, `SCHEDULER_AUTH_REQUIRED`**. Trading step: **SKIPPED**.
No tick/control/DB operation was performed. No secret value, length or fingerprint
was collected or logged.

Public Render verification: `/api/health` 200, OpenAPI contains the exact diagnostic
POST route. Missing/dummy scheduler credentials yield JSON
`{"detail":"SCHEDULER_AUTH_REQUIRED"}`, HTTP 401, without a Basic-auth challenge.
This is the application's `app/active43/api.py:scheduler` rejection, not Bitget,
Supabase or owner Basic authentication.

| Hop | Exact protocol |
| --- | --- |
| GitHub workflow | `.github/workflows/aura-active43.yml`, `operation=diagnostics` |
| Actions secret → environment | `AURA_ACTIVE43_BITGET_SCHEDULER_SECRET` → same name |
| Python source | `os.environ`, current job, no fallback to Auto42/Bybit/owner secret |
| Destination | `https://aura-traiding-terminal.onrender.com/api/active43/diagnostics/scheduler` |
| Method/header | POST / `X-Aura-Active43-Bitget-Token` |
| Server source | `os.getenv('AURA_ACTIVE43_BITGET_SCHEDULER_SECRET')` per request |
| Comparison | `secrets.compare_digest` on bytes, case-insensitive header lookup |

**Names, endpoint and header match. No hard-coded or cached old token exists in
this code path.** Changing a Render dashboard environment setting does not change
an already-running Python process's environment; the saved environment must be
applied through the owner's restart/deployment procedure. This is an operational
fact, **not proof** that it caused this particular incident.

## Limit of the current evidence

The deployed handler returns the same `SCHEDULER_AUTH_REQUIRED` for multiple
rejection branches and the old client discards the error body. Even run #6 cannot
prove which header/configuration the Render process actually received. There is
no authorized Render management or owner credential in this session.

Therefore:

- `AUTH_REJECTION_COMPONENT_VERIFIED = TRUE`.
- `CLIENT_PROTOCOL_VERIFIED = TRUE`.
- `EXACT_PRODUCTION_AUTH_REJECTION_BRANCH_VERIFIED = FALSE`.
- `PRODUCTION_SECRET_EQUALITY_VERIFIED = FALSE`.
- `PRODUCTION_AUTH_FIXED = FALSE` (not deployed or successfully authenticated).

Do not claim a stale Render secret, a mismatched pair, or a stripped header as an
established root cause. The existing response lacks that evidence. Repeating
secret creation/reset without it is not a verified correction.

## Implemented corrections

1. Scheduler client logs only fixed variable/header/endpoint names and safe
   presence/format/outer-whitespace/header-attached booleans in diagnostic mode.
2. Failed HTTP responses are bounded to 4096 bytes and parsed through an explicit
   code whitelist. Raw bodies/headers/exceptions are never printed. The error
   now distinguishes server codes instead of hiding everything behind HTTP 401.
3. Server returns separate codes:
   - `SCHEDULER_TOKEN_MISSING` — required header absent/empty;
   - `SCHEDULER_TOKEN_MISMATCH` — exactly one received token failed comparison;
   - `SCHEDULER_TOKEN_DUPLICATED` — repeated authorization header, rejected;
   - `SCHEDULER_ORIGIN_REJECTED` — browser/cross-site origin rejected;
   - `SCHEDULER_NOT_CONFIGURED` — invalid/missing/conflicting server secret, 503.
4. Rejection response contains only whitelisted component, header-received and
   origin-rejected flags, public protocol names and validated Render commit SHA.
   Never token values, lengths, hashes, raw headers or arbitrary environment.
5. Owner-only full diagnostics includes safe scheduler configuration: exact source
   variable/header, presence/format/outer-whitespace, conflicting **variable names**,
   per-request reads and process-restart requirement. No public account reads added.
6. Constant-time token comparison, independent scheduler authority, owner/CSRF
   controls, OFF/default settings and trading logic are preserved.

## Owner action

No new secret or SQL migration is required for this code change.

1. Review/approve this PR, merge only by owner decision, then in
   [Render Dashboard](https://dashboard.render.com/) deploy the new main commit
   with the already saved environment. Keep PAPER OFF. This session did neither.
2. In the [Aura 4.3 workflow](https://github.com/DOK123123/Aura-Traiding-Terminal/actions/workflows/aura-active43.yml)
   select **Run workflow → diagnostics**. Scheduler variable can remain false.
3. Read the precise code/evidence. `TOKEN_MISMATCH` is definitive evidence of an
   actual comparison failure in that running process; `TOKEN_MISSING` instead
   proves the header did not arrive. A successful response confirms authorization,
   but does not establish autonomous trades or justify automatically enabling PAPER.

If TOKEN_MISMATCH remains after the verified new commit is running, make the
existing saved Render value and Repository Actions secret of the **same exact
name** identical, apply the saved Render environment, and start a **new** diagnostic
workflow. Never send either value in chat. A rerun of an old workflow is not a
substitute for confirming which deployed commit/process is serving the request.

## Tests and review

See `AURA43_AUTH_RESULTS.json` for actual counts. Tests cover missing/wrong/old-scope
and duplicated headers, Origin rejection, correct auth with module OFF, runtime
token rotation on the same service instance, unconfigured server, sanitized
responses and logs. Whole Python and JavaScript suites are run; unchanged
PostgreSQL opt-in cases are explicitly reported as skipped, not claimed as tested.

Code/security self-review: no credential values emitted; no auth bypass/fallback;
no changes to Aura 4.2, Practice, strategy, risk, SQL, scheduler interval or portfolio;
no new secrets, production SQL, merge, deploy, PAPER activation or real orders.
The unresolved production verification above remains a deployment gate.

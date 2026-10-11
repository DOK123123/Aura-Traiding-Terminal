# ECC rules adapted for Aura

Adapted from ECC common coding-style/testing/security and Python
coding-style/testing/security/fastapi rules. See `UPSTREAM.md` and `LICENSE`.

## Keep scope and architecture stable

Plan from the existing call paths, list affected modules and test cases, then
make the smallest justified change. Keep market ingestion, pure analysis,
historical research and virtual-account reads separate. Do not import execution
or account credentials into public market-data providers. Existing static UI and
FastAPI construction are valid; no automatic create_app, ORM, JWT, React or
TypeScript migration. No style-only bulk rewrites or dependency churn.

## Python and FastAPI

Use clear names, specific exceptions, type annotations for new public interfaces
and context-managed resources. Preserve intentional exact-type checks that reject
bool as an integer; a generic isinstance recommendation must not weaken them.
Use asyncio locks for shared async state where needed, not blocking threading
locks inside coroutines. Do not perform blocking HTTP or expensive CPU work in
the event loop. Preserve task cancellation, lifespan cleanup and bounded timeouts.

Validate untrusted input at boundaries and whitelist account response fields.
Keep authentication enforced for every configured account read. Avoid credentialed
wildcard CORS. Default error messages/logs must be sanitized; never restore raw
exchange exception text or signed URLs for debugging. Keep amounts exact with
Decimal/strings in balances and any future order accounting; indicator floats
may remain with documented tolerances. Do not conflate quote and base units.

## Market and analysis invariants

Validate UTC interval alignment, monotonic order, finite positive prices,
high/low consistency, nonnegative valid volumes, duplicate/old events and gaps.
Missing gold volume is absence of evidence, not invented zero-volume evidence.
Treat provisional and closed candles distinctly. Never fill gaps with fake prices.
Use existing freshness contracts; stale, unsynchronized or source-mismatched data
must not be represented as actionable fresh signals. Preserve source labels when
switching providers and rebuild coherent windows rather than mixing providers.

For Binance REST/WebSocket, check server timestamps, pagination, duplicate events,
lost final candles, reconnect/resnapshot, bounded backoff and cancellation on
market change/disconnect. Rate limits must respect upstream cooldown. Account
reads use official Spot Testnet only, independently from production public quotes.

## Tests and review

Write meaningful tests for behavior, boundaries and important defects. Prefer
independent reference outputs over expectations copied from the implementation.
Do not weaken a test to hide a regression; fix incorrect old fixtures explicitly.
Offline mocks must cover timeout, invalid data/auth, rate limits, reconnection and
unconfigured Testnet. A passing unit test does not establish live connectivity.

The 80% ECC coverage target is a future measurement goal, not permission to invent
coverage, add redundant tests or block harmless documentation on absent tooling.
For execution-related changes, required tests and explicit code/security reviews
are mandatory, regardless of coverage. Review may recommend fixes but must not
silently change formulas, keys, permissions, strategy or execution modes.

## Future risk management boundary

No execution risk engine is implemented by this configuration. Before any future
order-writing implementation, specify and test per-order and total exposure,
position sizing, balance/quantity filters, rounding, loss limits, stale-data halt,
kill switch and duplicate-order protection. Checks must be deterministic outside
an LLM, fail closed and survive relevant restart/retry behavior. Do not treat
Stop Loss, Take Profit or a good signal score as substitutes for exposure limits.

Keep real-money execution prohibited by default. No automatic fallback from
Testnet to production and no authorization inferred from environment variables.

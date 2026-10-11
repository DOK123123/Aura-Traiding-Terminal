---
name: security-review
description: Review Aura credentials, account access and trading safety.
---

# Aura security-review

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Trace every credential from server environment to signed requests. Never expose API Secret, API keys, signatures, authenticated URLs or raw exchange exceptions in logs, browser responses, fixtures or GitHub.
- Preserve owner authentication, output whitelists, fixed HTTPS Testnet endpoints, GET-only operation and safe error mapping. Check redirects, SSRF, injection, XSS, rate limits and request timeouts.
- REAL MONEY TRADING is prohibited by default. Environment credentials are not permission to trade. Do not add order creation, modification, cancellation or transfers to the current read-only integration.
- Review environment/mode separation, freshness gating, idempotency and deterministic risk boundaries before any separately authorized execution work.
- Record concrete findings with file/location, impact and evidence. Unresolved critical/high findings or missing execution tests block integration. Consult docs/ecc/TRADING_REVIEW.md; do not install scanners or call external services automatically.

Adapted from ECC skills/security-review/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


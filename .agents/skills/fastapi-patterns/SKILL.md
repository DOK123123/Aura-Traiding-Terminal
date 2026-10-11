---
name: fastapi-patterns
description: Plan and review Aura FastAPI architecture and request boundaries.
---

# Aura fastapi-patterns

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Map ingestion, market state, analysis, account integration and HTML/JavaScript separately. Produce a small implementation plan with affected files, risks and validation before substantial changes.
- Keep Testnet isolated from public market providers. Preserve the fixed official Testnet host, GET allowlist and protected account routes.
- Check async lifecycle, timeouts, cancellation, dependency ownership, response validation and authentication. Missing credentials must leave the market terminal operational.
- Ensure chart and signal use matching symbol, interval, source and snapshot. Mark stale/provisional data explicitly; never treat a healthy HTTP response as proof of fresh exchange data.
- Use existing plain HTML/JavaScript and FastAPI patterns. Do not introduce an ORM, JWT, React or a new service solely to imitate upstream examples.

Adapted from ECC skills/fastapi-patterns/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


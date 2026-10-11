---
name: python-patterns
description: Review Python market-data and account code in Aura without changing strategy formulas.
---

# Aura python-patterns

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Inspect the actual call graph before proposing a change. Use docs/ecc/ROLES.md for planning and Python/code-review criteria.
- Validate types, finite OHLCV values, timestamp units, ordering and bounds at ingestion. Reject bool where an integer timestamp is required. Keep Decimal for account quantities; preserve existing indicator arithmetic.
- Check cancellation, bounded I/O, asyncio ownership and exception handling. Do not hide failures behind plausible prices or successful-looking account responses.
- Review small diffs for regressions and missing tests. Do not refactor working interfaces or change formulas merely to apply stylistic advice.

Adapted from ECC skills/python-patterns/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


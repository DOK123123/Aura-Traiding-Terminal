---
name: module-regression
description: Find hidden failures and downstream regressions in Aura.
---

# Aura module-regression

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Trace provider to market state/live API to indicators/patterns to UI, and Testnet reader to protected account API to account UI. Read actual consumers rather than guessing dependencies.
- Investigate swallowed exceptions, fallback source changes, cache age, timestamp conversion, reconnect races, duplicate bars, partial candles and misleading Connected status.
- Reproduce failures with small offline fixtures. Verify that a stale/mismatched signal cannot appear actionable and that account outages do not break market display.
- Compare before/after behavior and exercise affected consumers plus full regression suites. Distinguish absence of evidence from a confirmed working feature.
- Report file/function, trigger, impact and minimal correction. Use docs/ecc/ROLES.md for debugging/code review and docs/ecc/TRADING_REVIEW.md for trading calculations; do not create autonomous repair loops.

Adapted from ECC skills/module-regression/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


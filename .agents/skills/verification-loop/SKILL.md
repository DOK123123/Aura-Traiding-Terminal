---
name: verification-loop
description: Verify an Aura change with bounded checks and honest evidence.
---

# Aura verification-loop

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Read AGENTS.md and identify scope, baseline and affected consumers. Verify syntax/imports, full Python tests, both Node suites and changed JavaScript syntax as applicable.
- Check diff/file inventory, credential exposure, market-source consistency and unchanged Testnet read-only boundaries. Use offline mocks; no orders or live account traffic.
- Run optional lint/type/security tools only when already available and appropriate. Report unavailable checks as NOT RUN and distinguish baseline limitations from regressions.
- For instruction-only changes, confirm runtime files are byte-for-byte unchanged and instruction links/provenance are valid. Do not add tests that merely restate prose.
- Report commands, results, changed files and residual limitations. Commit/push only within user authorization; a passing test run does not authorize trading or deployment.

Adapted from ECC skills/verification-loop/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


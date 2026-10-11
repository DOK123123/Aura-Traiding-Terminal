---
name: python-testing
description: Test Aura calculations, data reliability and read-only account boundaries offline.
---

# Aura python-testing

Read the repository AGENTS.md first. This is instruction-only guidance, not an installed ECC agent or permission to execute actions.

- Use independent expected results for indicators and signals; test warmup, flat data, zero denominators, invalid OHLCV, duplicate/out-of-order bars and source mismatch.
- Mock exchange traffic and credentials. Exercise disconnect/reconnect, gaps, stale snapshots, timeouts, rate limits, clock skew, invalid keys and missing configuration.
- Preserve tests that prove only allowlisted GET endpoints can be used and secrets never reach responses/logs. Never place real or test orders in tests.
- Run python -m pytest -q and both existing Node suites. Additional coverage tools are optional if available; report absent tools as NOT RUN. Do not weaken assertions to achieve a pass.
- Future execution changes require deterministic sizing, precision, balance, exposure, loss-limit, duplicate/retry and restart tests plus both reviews in docs/ecc/TRADING_REVIEW.md.

Adapted from ECC skills/python-testing/SKILL.md, Affaan Mustafa, MIT, snapshot d4a44ded8c150aac89b37c1f665b5a749fe52b02. See docs/ecc/UPSTREAM.md and docs/ecc/LICENSE for attribution and full license.


---
name: ecc-full-audit
description: Evidence-based whole-repository Aura audit using pinned ECC review and verification guidance.
---

# Aura full audit — selective ECC adaptation

Upstream: https://github.com/affaan-m/ECC (original everything-claude-code URL).
Pinned source: b92f181b3b748d1abbc2afd94af6aa7d8c8fca29.
Copyright (c) 2026 Affaan Mustafa, MIT; full notice: docs/ecc/LICENSE.
Source mapping and file hashes: docs/ecc/AUDIT_UPSTREAM_MANIFEST.json.

Instruction-only adaptation of upstream agents/architect.md, planner.md,
python-reviewer.md, fastapi-reviewer.md, code-reviewer.md, security-reviewer.md,
tdd-guide.md, silent-failure-hunter.md; skills/python-testing, security-review,
verification-loop; rules/common/security, testing, development-workflow,
code-review and rules/python. No native plugin/CLI registration, hooks, MCP,
installer, agent model override or automatic execution is provided.

1. Read AGENTS.md and docs/ecc/{RULES,ROLES,TRADING_REVIEW}.md. Establish actual
   baseline files/hashes, route/dependency map, data provenance and test environment.
2. If explicitly authorized, use available independent Codex reviewers with
   scoped ownership. Record each role, actual upstream files read, commands,
   findings and evidence. Otherwise use separated passes and disclose that
   these were not independent agents. Do not invent native ECC agent execution.
3. Review security, Python/FastAPI, architecture, trading math, quant/research,
   frontend and QA. Trading/quant specialization is Aura guidance, not an ECC
   profitability certification. Treat reviewer reports as hypotheses until proved.
4. Severity follows demonstrated impact: CRITICAL/HIGH require correction or
   explicit blocker; template type hints/line counts/style do not become trading
   defects. Preserve exact-type validation, causality, formulas, risk limits,
   owner confirmation and virtual-only boundaries. No parameter optimization.
5. Reproduce defects before fixes. Narrow fixes require regression tests; keep
   historical results immutable and distinguish obsolete checkpoint/session
   hashes from data corruption. Never reset balances or rewrite PnL for success.
6. Adapt upstream verify phases to this Python/plain-JS repo: syntax/imports,
   full available pytest/unittest/Node/API/security/math/causality tests, dependency
   review, redacted secret scan and exact diff. Run tools only when available or
   safely isolated and user-authorized. No npm/TypeScript build for plain JS.
7. Cloud accommodations remain test-only. Report real counts and failures,
   unavailable coverage/lint/types/browser, package version differences and all
   limitations. Static tests are not Android/Render/browser validation.
8. Independent final review checks fixes and negative cases. Push only within
   explicit authorization after checks; no automatic deployment, external
   messages, hooks, real orders or strategy activation.

The user's explicit autonomous task authorization overrides upstream /plan's
extra confirmation gate; the planning/risk-grounding workflow still applies.
GitHub writes are allowed only by the user's task, never by upstream templates.
Do not copy ~/.codex settings, marketplace installers, telemetry or MCP defaults.

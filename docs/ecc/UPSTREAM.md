# Selective ECC adaptation for Aura

Upstream: https://github.com/affaan-m/ECC (the original everything-claude-code URL redirects here).
Pinned audited snapshot: d4a44ded8c150aac89b37c1f665b5a749fe52b02 (2026-10-11); upstream manifest version 2.2.3.
Copyright (c) 2026 Affaan Mustafa. MIT; full notice in LICENSE alongside this file.

This is a manually adapted, reduced instruction set, not a complete upstream installation. No runtime dependencies, installers, hooks, MCP servers, credential collection or autonomous actions are included.

## Source map

The six .agents/skills/*/SKILL.md files adapt their corresponding upstream skills/{name}/SKILL.md. They replace generic examples and commands with Aura-specific boundaries and offline checks.

ROLES.md adapts criteria from agents/architect.md, planner.md, python-reviewer.md, fastapi-reviewer.md, code-reviewer.md, security-reviewer.md, tdd-guide.md, code-explorer.md and silent-failure-hunter.md. These are review perspectives, not registered sub-agents.

RULES.md adapts rules/common/coding-style.md, testing.md, security.md and rules/python/coding-style.md, testing.md, security.md, fastapi.md.

AGENTS.md combines those criteria with Aura's project map and user-authorized safety policy. TRADING_REVIEW.md is Aura-specific guidance added for market data, indicators, Testnet and possible future execution; upstream does not certify Aura's financial calculations.

## Codex use

Root AGENTS.md explicitly points to every selected skill and review document. Skills are stored in the conventional .agents/skills layout; automatic discovery depends on the Codex client/environment. If Cloud does not discover them, read the linked instructions explicitly. This configuration does not require local Codex CLI and does not promise CLI plugin/hook functionality in Cloud.

No .codex configuration, native plugin, upstream .mcp.json, hooks, memory services, learning loops or integrations/aura package is enabled. That upstream Aura integration is unrelated to Aura Trading Terminal.

Updates are manual: review a new pinned upstream revision, retain notices, inspect the diff, and run Aura verification before integration. These documents guide development; existing runtime safeguards remain responsible for enforcement.

# Review roles for Aura

Adapted from ECC agents listed in `UPSTREAM.md`; MIT notice in `LICENSE`.
These are review checklists for the current session, not registered background
agents. They do not grant tools, change models, spawn reviewers or run commands.
Use explicit separate review passes when helpful; delegate only when the user
and host authorize delegation. Ordinary review reports findings without editing.

| Role | ECC source | Aura scope |
| --- | --- | --- |
| Architecture/planning | architect, planner | Trace current dependencies, contracts, state and deployment limits; propose bounded changes, alternatives and acceptance checks without automatic refactoring. |
| Python review | python-reviewer | Exceptions, strict validation, async state, cancellation, resources, numerical units and maintainability; preserve exact-type validation and formulas. |
| FastAPI review | fastapi-reviewer | Lifespan cleanup, HTTP/WebSocket contracts, async I/O, account authentication, input/output validation and safe error responses. |
| Code review | code-reviewer | Inspect the intended diff and callers; prove actionable findings, check changed source, tests and scope together. |
| Security review | security-reviewer | Environment-only credentials, fixed Testnet host/GET allowlist, redirects/TLS, owner access, secret redaction, browser XSS and accidental production authority. |
| Testing | tdd-guide | Reproduce defects; write offline mocks and independent reference cases; verify affected downstream components without weakening assertions. |
| Debugging/hidden errors | code-explorer, silent-failure-hunter | Trace ingestion → window → analysis → frontend; hunt swallowed errors, misleading cache/fallback, silent socket stalls and stale scores. |

For each pass report severity, file/function, evidence, practical impact and a
specific recommendation. Separate confirmed defects, unverified concerns and
style suggestions. State checks run or NOT RUN and residual risks. A role name
is not evidence that review occurred. Do not replace credentials-safe errors with
full exception/response dumps to satisfy a generic debugging checklist.

Any future change to order creation, cancellation, modification, execution
retries, exchange selection, sizing or execution permissions must undergo both
code and security review after tests and before integration. Applying that gate
does not authorize implementing an execution feature in the current task.

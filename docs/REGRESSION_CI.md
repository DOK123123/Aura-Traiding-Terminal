# Regression CI

`.github/workflows/regression.yml` runs for every pull_request update (including
draft PRs) and push to main. It explicitly checks out the PR head SHA or pushed
main SHA. It does not merge, deploy, dispatch a trading workflow, initialize a
production account or access any production API/secret. Permissions are read-only.

Python follows `.python-version` (3.12). Node is pinned in `.node-version`, matching
the documented/tested Node 24.19.0 runtime. `ci/requirements.lock` pins all direct
and transitive Python dependencies, including pip. Installation uses `--no-deps`
and `pip check`; a gate verifies direct pins still match `requirements.txt`.
The production requirements and application code are unchanged.

The commands remain `python -m pytest -q` and `node --test tests/*.cjs`, with
JUnit output. All three real-PostgreSQL opt-ins are enabled. The existing SQL
test harnesses create isolated Docker **service containers**, with network=none,
no published ports, dedicated databases and cleanup. A reusable Actions
`services.postgres` database would not work with their intentional crash/restart
and isolation guards; the CI reuses their existing container lifecycle instead
of weakening it or substituting production Supabase.

The pinned PostgreSQL image is pulled before entering the test network namespace.
Tests run with loopback enabled but no external network. Only the local Unix
Docker socket is used for SQL; offline HTTP/scheduler/Worker fixtures communicate
over loopback. Runtime packages, Actions and artifact upload use networking in
separate setup/report steps. No production credential is supplied to any step.

Both suites must execute and pass. Missing/empty reports, any skipped/todo/error
or failing test, or a nonzero suite exit status fail the job. No test skip is
counted as PASS. `ci-results/summary.json` is written only after actual successful
nonempty zero-skip reports. JUnit and summary artifacts are retained for 7 days.

If the workflow is absent, inspect the PR event/head SHA and Actions permissions;
if queued/blocked, report that actual state. A local test run is never a GitHub
CI pass. A skipped external Supabase Preview is not this regression check.

CI changes do not alter strategies, risk, balances, SQL, Render, Supabase,
Cloudflare or trading scheduler settings. Synthetic fixture trades remain only
inside the isolated regression environment.

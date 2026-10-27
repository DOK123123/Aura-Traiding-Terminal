#!/usr/bin/env bash
set -euo pipefail
# Invoked only by regression CI inside an isolated network namespace.
python_bin=$1
node_bin=$2
test_dir=$3
# sudo uses its own secure_path. Nested HTTP/Worker fixtures also invoke bare
# node/python commands, so retain the exact setup runtimes for every subprocess.
export PATH="$(dirname "$node_bin"):$(dirname "$python_bin"):$PATH"
export AURA_ACTIVE43_VERIFY_POSTGRES=true
export AURA_AUTO42_VERIFY_POSTGRES=true
export AURA_PRACTICE_VERIFY_POSTGRES=true
export AURA_MANUAL_PAPER_VERIFY_POSTGRES=true
export TZ=UTC
mkdir -p ci-results

# Existing PostgreSQL harnesses create their own disposable service containers
# with --network none, no exposed ports and isolated fixed test databases. They
# intentionally restart those services; never substitute hosted Supabase.
python_status=0
"$python_bin" -m pytest -q --junitxml=ci-results/python.xml --basetemp="$test_dir" || python_status=$?
node_status=0
"$node_bin" --test --test-reporter=junit --test-reporter-destination=ci-results/javascript.xml tests/*.cjs || node_status=$?
test "$python_status" -eq 0
test "$node_status" -eq 0
"$python_bin" ci/check_results.py ci-results/python.xml ci-results/javascript.xml

# The runner image supplies Chrome. Fail rather than claiming a mobile PASS if
# it is missing. This script already runs inside the loopback-only namespace.
browser_bin="$(command -v google-chrome || command -v chromium || true)"
test -n "$browser_bin"
"$python_bin" scripts/verify_manual_trader5_browser.py --browser "$browser_bin" --output-dir ci-results/manual-trader5-browser

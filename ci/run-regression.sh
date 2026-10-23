#!/usr/bin/env bash
set -euo pipefail
# Invoked only by regression CI inside an isolated network namespace.
python_bin=$1
node_bin=$2
test_dir=$3
export AURA_ACTIVE43_VERIFY_POSTGRES=true
export AURA_AUTO42_VERIFY_POSTGRES=true
export AURA_PRACTICE_VERIFY_POSTGRES=true
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

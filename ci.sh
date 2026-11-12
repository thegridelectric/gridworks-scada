#!/usr/bin/env bash
#
# The gate for this repo: the GitHub workflow runs this script for its
# checks, so a local pass is a CI pass. Run it before committing.
#
# The tests need the two mosquitto brokers on localhost:1883 and
# localhost:18831 (README "Testing"). Arguments go to pytest.
#
# Usage: ./ci.sh [pytest args]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

step() { printf '\n=== %s ===\n' "$1"; shift; "$@"; }

step "uv sync (locked)" uv sync --locked
step "ruff check" uv run --locked ruff check --no-fix --no-cache .
step "pytest" uv run --locked coverage run -m pytest "$@"

printf '\nAll checks passed.\n'

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "== ruff check =="
ruff check

echo "== pytest =="
coverage run -m pytest "$@"

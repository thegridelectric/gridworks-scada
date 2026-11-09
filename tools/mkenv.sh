#!/usr/bin/env bash
# Helper script to create or update the scada virtual env (.venv) from uv.lock.
#
# Run from top level of repo.

if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or update the scada virtual env (.venv) from uv.lock."
  echo
  echo "Run from top level of repo."
  echo
  echo "Usage: $0 [uv sync options]"
  echo
  echo "The interpreter is the one .python-version names; uv downloads it if"
  echo "no matching Python is installed."
  echo
  exit 0
fi

set -euo pipefail
uv sync --locked "$@"
rm -f .venv/bin/gws
ln -s "$(pwd)/gw_spaceheat/gws" .venv/bin

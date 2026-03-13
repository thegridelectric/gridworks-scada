#!/usr/bin/env bash

set -euo pipefail

WAIT_SECONDS="${WAIT_SECONDS:-0.5}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "Error: tmux is not installed."
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "Usage: $(basename "$0") <session_name>"
  echo
  echo "Example: $(basename "$0") honeycrisp"
  echo "Starts/restarts tmux session 'honeycrisp' using repos under:"
  echo "  \$HOME/ltn-honeycrisp/gridworks-scada"
  echo "  \$HOME/ltn-honeycrisp/gridworks-innovations"
  exit 0
fi

if [[ $# -gt 1 ]]; then
  echo "Error: expected at most one argument: <session_name>"
  exit 1
fi

if [[ $# -eq 1 ]]; then
  session_name="$1"
else
  cwd="$(pwd)"
  parent_dir="$(basename "$(dirname "$cwd")")"
  if [[ "$(basename "$cwd")" == "gridworks-scada" && "$parent_dir" == ltn-* ]]; then
    session_name="${parent_dir#ltn-}"
    echo "No session name provided; inferred '$session_name' from current directory."
  else
    echo "Error: missing required argument <session_name>."
    echo "Run from anywhere as: $(basename "$0") <session_name>"
    exit 1
  fi
fi

repo_root="$HOME/ltn-$session_name/gridworks-scada/gw_spaceheat"
if [[ -z "$session_name" ]]; then
  echo "Error: session_name cannot be empty."
  exit 1
fi

venv_activate="$repo_root/venv/bin/activate"
if [[ ! -f "$venv_activate" ]]; then
  echo "Error: venv activate script not found at:"
  echo "  $venv_activate"
  exit 1
fi

if tmux has-session -t "$session_name" 2>/dev/null; then
  echo "Existing tmux session '$session_name' found; clearing it."
  tmux kill-session -t "$session_name"
  sleep "$WAIT_SECONDS"
fi

ltn_scada_repo="$HOME/ltn-$session_name/gridworks-scada"
ltn_innovations_repo="$HOME/ltn-$session_name/gridworks-innovations"

for repo_dir in "$ltn_scada_repo" "$ltn_innovations_repo"; do
  if [[ ! -d "$repo_dir/.git" ]]; then
    echo "Error: expected git repo not found at:"
    echo "  $repo_dir"
    exit 1
  fi
  echo "Updating repo: $repo_dir"
  git -C "$repo_dir" pull --ff-only
done

tmux new-session -d -s "$session_name"
sleep "$WAIT_SECONDS"

tmux send-keys -t "$session_name" "cd \"$repo_root\"" C-m
sleep "$WAIT_SECONDS"

tmux send-keys -t "$session_name" "source \"$venv_activate\"" C-m
sleep "$WAIT_SECONDS"

tmux send-keys -t "$session_name" "python" C-m
sleep "$WAIT_SECONDS"

tmux send-keys -t "$session_name" "from actors.ltn.config import LtnSettings; from ltn_app import LtnApp; import dotenv" C-m
sleep "$WAIT_SECONDS"

tmux send-keys -t "$session_name" "l = LtnApp.get_repl_app(app_settings=LtnSettings(_env_file=dotenv.find_dotenv())).ltn" C-m

echo "Started tmux session '$session_name' and initialized Ltn REPL."
echo "Attaching now..."
tmux attach -t "$session_name"

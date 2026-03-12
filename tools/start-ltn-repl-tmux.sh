#!/usr/bin/env bash

set -euo pipefail

WAIT_SECONDS="${WAIT_SECONDS:-0.25}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "Error: tmux is not installed."
  exit 1
fi

repo_root="$(pwd)"
if [[ "$(basename "$repo_root")" != "gridworks-scada" ]]; then
  echo "Error: run this script from the gridworks-scada directory."
  echo "Current directory: $repo_root"
  exit 1
fi

parent_dir="$(basename "$(dirname "$repo_root")")"
session_name="${parent_dir#ltn-}"
if [[ -z "$session_name" ]]; then
  echo "Error: could not infer tmux session name from parent directory: $parent_dir"
  exit 1
fi

venv_activate="$HOME/ltn-$session_name/gridworks-scada/gw_spaceheat/venv/bin/activate"
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

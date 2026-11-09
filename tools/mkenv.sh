
dev_requirements=gw_spaceheat/requirements/dev.txt
PYTHON="${PYTHON:-python}"
# error (default) or warn. mkenv-pi.sh warns: a deployed Pi keeps the
# Raspberry Pi OS interpreter, which may differ from the laptop/CI pin.
PYTHON_VERSION_MISMATCH="${PYTHON_VERSION_MISMATCH:-error}"

if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or recreate the scada virtual env."
  echo
  echo "Run from top level of repo."
  echo
  echo "Usage: $0 [requirements file (default: $dev_requirements)]"
  echo
  echo "PYTHON must match .python-version (major.minor)."
  echo "PYTHON_VERSION_MISMATCH=warn reports a mismatch and continues."
  echo
  exit 0
fi

# The port of this script to uv, and the deployment facts it has to keep,
# are OPS-661 (scada-to-uv).
pin_file="$(cd "$(dirname "$0")/.." && pwd)/.python-version"
if [[ ! -f "$pin_file" ]]; then
  echo "error: missing $pin_file" >&2
  exit 1
fi
required="$(tr -d '[:space:]' < "$pin_file")"
IFS=. read -r major minor _ <<<"$required"
required_mm="${major}.${minor}"
if ! actual_mm="$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"; then
  echo "error: cannot run $PYTHON" >&2
  exit 1
fi
if [[ "$actual_mm" != "$required_mm" ]]; then
  message="$PYTHON is Python $actual_mm; .python-version requires $required_mm"
  if [[ "$PYTHON_VERSION_MISMATCH" == "warn" ]]; then
    echo "warning: $message" >&2
  else
    echo "error: $message" >&2
    exit 1
  fi
fi

rm -rf gw_spaceheat/venv
$PYTHON -m venv gw_spaceheat/venv
source gw_spaceheat/venv/bin/activate
which pip
pip install --upgrade pip
pip install -r ${1:-$dev_requirements}
pip install -e packages/gridworks-scada-protocol
if [ "${2:-install_admin}" == "install_admin" ]
then
  pip install -e packages/gridworks-admin
fi
rm gw_spaceheat/venv/bin/gws > /dev/null 2>&1
ln -s `pwd`/gw_spaceheat/gws gw_spaceheat/venv/bin

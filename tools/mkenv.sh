
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

# TODO: port this script to uv so setup installs the interpreter named in
# .python-version instead of using whatever python is on PATH. Deployment
# has to keep working when that happens:
# - service/gwspaceheat.service and service/gwltn@.service exec
#   gw_spaceheat/venv/bin/python at a fixed path on the Pi and the LTN box.
#   The venv has to stay at that path.
# - Pis are provisioned with mkenv-pi.sh and the distro interpreter
#   (docs/provisioning.md). drivers.in installs board and Adafruit libraries
#   against that system Python. A field Pi may not have uv, and provisioning
#   should not need a separate CPython download.
# - scripts/roll.sh rebuilds box venvs with this script and expects the
#   editable install of the ../optimal-flexibility sibling.
# - Laptops and Pis keep separate pip-tools locks (dev.txt and drivers.txt).
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

# bruce, the FLO (optimal-flexibility): installed editable from the sibling
# checkout ../optimal-flexibility by default, on the laptop as on a box, so
# a bruce update is a pull of the sibling; every recommendation records
# the sibling's commit. "no_flo" skips it.
INSTALL_FLO="${3:-editable_flo}"

if [ "$INSTALL_FLO" == "editable_flo" ]
then
  pip install -e ../optimal-flexibility/
fi

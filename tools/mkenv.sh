
dev_requirements=gw_spaceheat/requirements/dev.txt
PYTHON="${PYTHON:-python}"

if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or recreate the scada virtual env."
  echo
  echo "Run from top level of repo."
  echo
  echo "Usage: $0 [requirements file (default: $dev_requirements)] [install_admin|no_admin] [install_flo|no_flo]"
  echo
  echo "install_flo (default): editable install of optimal-flexibility from"
  echo "  ../optimal-flexibility (e.g. ~/ltn-oak/) or ../../optimal-flexibility, or"
  echo "  OPTIMAL_FLEXIBILITY_PATH if set."
  echo
  exit 0
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

INSTALL_FLO="${3:-install_flo}"

if [ "$INSTALL_FLO" == "install_flo" ]
then
  flo_repo="${OPTIMAL_FLEXIBILITY_PATH:-}"
  if [ -z "$flo_repo" ]; then
    if [ -f "../optimal-flexibility/pyproject.toml" ]; then
      flo_repo="../optimal-flexibility"
    elif [ -f "../../optimal-flexibility/pyproject.toml" ]; then
      flo_repo="../../optimal-flexibility"
    fi
  fi
  if [ -z "$flo_repo" ] || [ ! -f "$flo_repo/pyproject.toml" ]; then
    echo "Error: optimal-flexibility not found."
    echo "  Clone it next to this repo (../optimal-flexibility, as in ~/ltn-oak/)"
    echo "  or set OPTIMAL_FLEXIBILITY_PATH to the repo root."
    exit 1
  fi
  pip install -e "$flo_repo"
fi

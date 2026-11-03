
dev_requirements=gw_spaceheat/requirements/dev.txt
PYTHON="${PYTHON:-python}"

if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or recreate the scada virtual env."
  echo
  echo "Run from top level of repo."
  echo
  echo "Usage: $0 [requirements file (default: $dev_requirements)]"
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

# bruce, the FLO (optimal-flexibility): installed editable from the sibling
# checkout ../optimal-flexibility by default, on the laptop as on a box, so
# a bruce update is a pull of the sibling; every recommendation records
# the sibling's commit. "no_flo" skips it.
INSTALL_FLO="${3:-editable_flo}"

if [ "$INSTALL_FLO" == "editable_flo" ]
then
  pip install -e ../optimal-flexibility/
fi

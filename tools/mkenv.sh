
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
pip install -e packages/gridworks-admin
rm gw_spaceheat/venv/bin/gws > /dev/null 2>&1
ln -s `pwd`/gw_spaceheat/gws gw_spaceheat/venv/bin


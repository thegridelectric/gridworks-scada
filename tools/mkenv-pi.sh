# Helper script to create or recreate the scada virtual env on the pi
#
# Run from top level of repo.
if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or recreate the scada virtual env on the pi."
  echo
  echo "Run from top level of repo."
  echo
	echo "Usage: $0"
	exit 0
fi

./tools/mkenv.sh "gw_spaceheat/requirements/drivers.txt"

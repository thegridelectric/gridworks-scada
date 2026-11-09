# Helper script which restore virtual env on the pi to using gwproto and
# gwproactor as locked in uv.lock.
#
# Run from top level of repo.
if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script which restore virtual env on the pi to using gwproto and gwproactor as locked in uv.lock."
  echo
  echo "Run from top level of repo."
  echo
	echo "Usage: $0"
	exit 0
fi

tools/rpro.sh --no-dev --group drivers

#!/usr/bin/env bash
# Helper script to create or update the scada virtual env on the pi: the
# runtime dependencies and the drivers group, without the dev group.
#
# Run from top level of repo.

if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script to create or update the scada virtual env on the pi."
  echo
  echo "Run from top level of repo."
  echo
	echo "Usage: $0"
	exit 0
fi

./tools/mkenv.sh --no-dev --group drivers

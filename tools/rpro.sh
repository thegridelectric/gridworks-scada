if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script which restore virtual env to using gwproto and gwproactor as locked in uv.lock."
  echo
  echo "Run from top level of repo."
  echo
	echo "Usage: $0 [uv sync options]"
	exit 0
fi

uv sync --locked "$@" --reinstall-package gridworks-proactor --reinstall-package gridworks-protocol
.venv/bin/python -c "import gwproto; import gwproactor; print(gwproto.__file__); print(gwproactor.__file__)"

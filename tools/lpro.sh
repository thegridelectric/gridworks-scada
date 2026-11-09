if [[ ( $@ == "--help") ||  $@ == "-h" ]]
then
  echo "Helper script which updates virtual env to use local copy of gwproto and gwproactor"
  echo
  echo "Run from top level of repo."
  echo
  echo "Usage: $0"
  echo
  exit 0
fi

uv pip install --no-cache -e ../gridworks-proactor -e ../gridworks-protocol
.venv/bin/python -c "import gwproto; import gwproactor; print(gwproto.__file__); print(gwproactor.__file__)"

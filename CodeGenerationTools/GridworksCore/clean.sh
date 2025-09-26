
pushd ../..

isort gw_spaceheat/named_types
black gw_spaceheat/named_types
ruff check gw_spaceheat/named_types --fix

popd
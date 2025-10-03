## Scada Packages

Motivated by the need to make [gridworks-admin] installable without setting up the
scada development environment, this directory contains code published on PyPI as
separate [distribution packages]. The separate distribution packages are managed
as separate python projects, each with their own subdirectory, each containing
its own [pyproject.toml]. Subproject development is done using [uv] and
publication to PyPI happens [in CI] after merging to the main branch. 

Currently there are two packages: 
1. [gridworks-admin], the admin user interface, and
2. [gridworks-scada-protocol], which contains protocol messages shared by both
   Scada and admin. 

## Developing

Install uv per [this]. Each subproject is its  own uv project. To do uv
operations on the subproject, cd to its directory and then run the uv command,
for example:

```shell
cd packages/gridworks-admin
uv version
```

The subprojects are *not* developed as part of a [uv workspace] because the
scada repo itself is not a uv project. If the scada repo is modified to us uv,
the subprojects can be converted to workspace projects per the workspace
documentation.

### Scada virtualenv
The subprojects are installed in the **scada** development environment in
editable mode by [mkenv.sh]. For example, all these commands access the 
subprojects and work from the scada development environment:

```shell
gwa
gws admin
python -c "import gwsproto"
pytest
```

While changes from source are automatically reflected in the scada development
environment, changes to subproject's pyproject.toml are not. If you modify a
subproject's pyproject.toml, for example by adding a dependency or by adding a 
[command line script], those changes will *not* be reflected in the scada
development environment until you either: 
1. Reinstall the subproject in editable mode, for example: 
   ```shell
   pip install -e packages/gridworks-admin
   ```
2. Recreate the scada development environment with: 
   ```shell
   tools/mkenv.sh
   ```

### Subproject virtualenvs
You can *usually ignore* the environments created in the subprojects by uv. 

Some uv operations require a local virtual environment *for the subproject* and
will automatically create one in the subproject directory, for example:

```shell
cd packages/gridworks-admin
uv version --bump patch
```
will create a virtual environment in `packages/gridworks-admin/.venv`. If you 
find you need to us that enviroment you can use `uv run`. For example, to run 
admin in its uv virtual environment run: 
```shell
uv run gwa
```
or you can activate the enviroment inside the shell with:
```shell
source .venv/bin/activate
```

## Adding dependencies

## Testing
Test the subprojects by running `pytest` from the repository root. 

Subprojects tests are currently in the repositorie's top level [tests] directory,
*not* inside the subprojects. This is primarily because the admin tests need to
include interactions with the scada code.

## Publishing

To publish a new version admin to PyPI:
1. Update the version field in the [admin pyproject.toml], either using
   the [uv version] command, for example:
   ```shell
   cd packages/gridworks-admin
   uv version --bump patch
   ```
   or by manually modifying the pyproject.toml and then running `uv lock`.
2. Merge to main. 



[distribution packages]: https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#distribution-package-vs-import-package
[uv]: https://docs.astral.sh/uv/
[pyproject.toml]: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
[in CI]: https://github.com/thegridelectric/gridworks-scada/blob/dev/.github/workflows/release.yml
[gridworks-scada-protocol]: https://pypi.org/project/gridworks-scada-protocol/
[gridworks-admin]: https://pypi.org/project/gridworks-admin/
[this]: https://docs.astral.sh/uv/getting-started/installation/#standalone-installer
[uv workspace]: https://docs.astral.sh/uv/concepts/projects/workspaces/
[mkenv.sh]: ../tools/mkenv.sh
[tests]: https://github.com/thegridelectric/gridworks-scada/tree/dev/tests
[command line script]: https://github.com/thegridelectric/gridworks-scada/blob/9c7f3ded7d8a08868a8be17a36f27fc32fcff704/packages/gridworks-admin/pyproject.toml#L23
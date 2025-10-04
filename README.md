# GridWorks SCADA

[![Tests](https://github.com/thegridelectric/gridworks-scada/actions/workflows/ci.yaml/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/thegridelectric/gridworks-scada/branch/main/graph/badge.svg)][codecov]

[tests]: https://github.com/thegridelectric/gridworks-scada/actions/workflows/ci.yaml
[codecov]: https://app.codecov.io/gh/thegridelectric/gridworks-scada
========


This code is intended for running a heat pump thermal storage space heating system in a house, and doing this _transactively_. That means the heating system is capable of dynamically responding to local electric grid conditions and buying energy at the lowest cost times, while keeping the house warm. We believe this repo may be instrumental in effectively and efficiently reaching a low-carbon future. For an architectural overview of the code, and why it has something to do with a low-carbon future, please go [here](docs/architecture-overview.md).

This code is part of a larger framework. In particular it assumes there is a cloud-based actor which it refers to as the [AtomicTNode](docs/atomic-t-node.md) (short for Atomic Transactive Node) that is calling the shots on its control decisions most of the time. In addition, the code is structured in an
actor-based way, with a  collection of actors each responsible for an important but limited set
of functionality communicating to each other via messages. For a more specific description of both how these internal actors work with each other and how 
this repo fits into the larger transactive energy framework please go [here](docs/core-protocol-sequences.md); this page describes typical sequences of messages between relevant actors in the system.

 We are indebted to Efficiency Maine, who spearheaded and funded the [initial pilot](docs/maine-heat-pilot.md) using this code. As per the requirements of the initial pilot, the code is intended to:
  1) run on a raspberry Pi 4; and 
  2) to be able to use a variety of off-the-shelf actuating and sensing devices.

For information on setting up an SD card that will run this code on a Pi 4 with the correct
configuration and attached devices, please [go here](docs/setting-up-the-pi.md)


## Creating a Dev environment for macos or Pi

Use python 3.11

Create the development environment with: 
    
    tools/mkenv.sh

On a Pi run:
    
    tools/mkenv-pi.sh

To activate the environment, add 'gw_spaceheat' to your PYTHONPATH and then 
`source` the environment's activation file. This is most easily accomplished
with a shell alias, for example on a Mac by fixing to following to contain the 
actual the path to this repo on your machine and then adding the result to  
`$HOME/.zprofile`:

    export SCADA_REPO=actual/path/to/your/repo
    export GW_SPACEHEAT=$SCADA_REPO/gw_spaceheat
    alias gw="source $GW_SPACEHEAT/venv/bin/activate && export PYTHONPATH=$GW_SPACEHEAT && cd $SCADA_REPO"

You will then be able to activate the development environment in a new terminal
with: 

```shell
gw
```


Run the tests from the root directory of the repo with:

```shell
pytest
```

A hardware layout file is necessary to run the scada locally. Find the default path the layout file with: 

```shell
python -c "from gwproactor.config.paths import Paths; print(Paths().hardware_layout)"
```    

For initial experiments the test layout file can be used. The test layout file is located at:
    
    tests/config/hardware-layout.json

Display the hardware layout with:

```shell
gws layout show
```    

Display current settings with: 
    
```shell
gws config
```

There are some scratch notes on Pi-related setup (like enabling interfaces) in docs/pi_setup.md

### Adding libraries 
Add libraries by adding the library spec to the appropriate ".in" file in the 
[requirements directory](./gw_spaceheat/requirements). Use:

* [dev.in](./gw_spaceheat/requirements/dev.in) for requirements only needed for
  development or CI. 
* [drivers.in](./gw_spaceheat/requirements/drivers.in) for requirements only
  needed on a Pi. 
* [base.in](./gw_spaceheat/requirements/base.in) for requirements used used
  in all contexts. 

Once you have added your requirement run: 

    tools/pipc.sh

Then **manually** modify the modified .txt files to remove the absolute paths
that pip-tools adds to comments inside the .txt files. This allow someone looking
at the commit to see only the dependency you changed. Otherwise they will see a 
change in the comment many dependencies. For example, in a text editor or IDE
do a search/replace in *.txt files in the project, searching for the text
    
    path/to/scada/repo/on/your/machine/gw_spaceheat

and replacing it with
    
    gw_spaceheat

### Handling secrets and config variables
    
SETTING UP SECRETS.
Configuration variables (secret or otherwise) use dotenv module in a gitignored `.env` file, copied over from `.env-template`. These are accessed via `config.ScadaSettings`.


### Setting up MQTT

See instructions [here](https://gridworks-proactor.readthedocs.io/en/latest/#mosquitto) to set up a local MQTT broker
using [Mosquitto](https://mosquitto.org/).


### Static analsyis with ruff

[Ruff](https://docs.astral.sh/ruff/) is installed via the test and dev requirements. 
You can run it with:

```shell
ruff check
```

Ruff is *not* run in CI or in pre-commit, since the code will not currently pass. 
Ruff is provided primarily for visual feedback in the IDE. Ruff is configured
in `pyproject.toml`.


### Static analysis in Visual Studio Code

Visual Studio Code will provide visual feedback on code that does not pass ruff.

To use this functionality, the [ruff plugin](https://github.com/astral-sh/ruff-vscode)
for Visual Studio code must be installed. We recommend: 

1. Installing the ruff extension. 
2. Disabling it. 
3. Enabling for workspaces in which you want to use it, such as this one. 

### More static analysis

More rigid ruff rules can be applied by modifying pyproject.toml. Gwproto, for
example, uses [many more rules](https://github.com/thegridelectric/gridworks-protocol/blob/fb7e1a3d17073aad647c223730c41495e6238fd8/pyproject.toml#L124).

Typechecking feedback can be applied in the IDE by enabling Pylance type checking
inside [vscode](vscode://settings/python.analysis.typeCheckingMode). Change that
in *user* not workspace settings since much of the code will currently fail. 

#### TLS

TLS is used by default. Follow [these instructions](https://gridworks-proactor.readthedocs.io/en/latest/#tls) to set up
a local self-signed Certificate Authority to create test certificates and to create certificates for the Mosquitto
broker. Note that [this section](https://gridworks-proactor.readthedocs.io/en/latest/#external-connections)
is relevant if you will connect to the Mosquitto broker from a Raspberry PI.

##### Create a certificate for the test ATN

```shell
gwcert key add --certs-dir $HOME/.config/gridworks/atn/certs scada_mqtt
cp $HOME/.local/share/gridworks/ca/ca.crt $HOME/.config/gridworks/atn/certs/scada_mqtt
```

##### Create a certificate for test Scada

```shell
gwcert key add --certs-dir $HOME/.config/gridworks/scada/certs gridworks_mqtt
cp $HOME/.local/share/gridworks/ca/ca.crt $HOME/.config/gridworks/scada/certs/gridworks_mqtt                    
```

##### Test generated certificates

In one terminal run: 
```shell

mosquitto_sub -h localhost -p 8883 -t foo \
     --cafile $HOME/.config/gridworks/atn/certs/scada_mqtt/ca.crt \
     --cert $HOME/.config/gridworks/atn/certs/scada_mqtt/scada_mqtt.crt \
     --key $HOME/.config/gridworks/atn/certs/scada_mqtt/private/scada_mqtt.pem

```
In another terminal run: 
```shell
mosquitto_pub -h localhost -p 8883 -t foo -m '{"bar":1}' \
     --cafile $HOME/.config/gridworks/scada/certs/gridworks_mqtt/ca.crt \
     --cert $HOME/.config/gridworks/scada/certs/gridworks_mqtt/gridworks_mqtt.crt \
     --key $HOME/.config/gridworks/scada/certs/gridworks_mqtt/private/gridworks_mqtt.pem

```

Verify you see `{"bar":1}` in the first window. 

#### Configuring a Scada with keys that can be used with the GridWorks MQTT broker. 

Use [getkeys.py](https://github.com/thegridelectric/gridworks-scada/blob/main/gw_spaceheat/getkeys.py) to
create and copy TLS to keys to a scada such that it can communicate with the actual GridWorks MQTT broker. For details
run: 
```shell
python gw_spaceheat/getkeys.py --help
```

The overview of this process is that you need: 
1. The ssh key for `certbot`.
2. [rclone](https://rclone.org/install/) installed. 
3. An rclone remote configured for your scada. 
4. To construct the `getkeys.py` command line per its help. 

## Running the code

This command will show information about what scada would do if started locally: 
```shell
gws run --dry-run  
```

This command will will start the scada locally: 
```shell
gws run
```

These commands will start the local test ATN:
```shell
gws atn run
```

## Development flow

Default branch is dev. Make PRs to this branch for review from your code branch. Make bug changes directly to this branch.
The first 5 homes in Millinocket are designed for beta testing. The idea here is that they run on dev, and the larger
group of houses run on main.

The main branch is protected - requires a pull request. Default pattern is PRs from dev to main.
This will also publish a new gridworks-scada-protcol package and a new grdiworks-admin package.

## Packages

Motivated by the need to make [gridworks-admin] installable without setting up the
scada development environment, this repository contains a [packages](./packages)
directory for code published on PyPI as separate [distribution packages]. The
separate distribution packages are managed as separate by python projects, with
their own subdirectory, each containing its own [pyproject.toml]. Subproject
development is done using [uv] and publication to PyPI happens [in CI] after 
merging to the main branch. 

There are two packages: 
1. [gridworks-admin], the admin user interface.
2. [gridworks-scada-protocol], which contains protocol messages shared by both
   Scada and admin. 

See the [packages directory README.md](./packages/README.md) for more information.

## Admin

To install admin as a tool separate from development environment: 

```shell
uv tool install gridworks-admin
```

or

```shell
pipx install gridworks-admin
```

To run admin from the development environment: 

```shell
gwa
```

To publish a new version admin to PyPI [install uv], if necessary, and then:
1. Update the version field in the [admin pyproject.toml], either using
   the [uv version] command, for example:
   ```shell
   cd packages/gridworks-admin
   uv version --bump patch
   ```
   or by manually modifying the pyproject.toml and then running `uv lock`.
2. Merge to main. 

See the [packages directory README.md](./packages/README.md) for more information.

## License

Distributed under the terms of the [MIT license](./LICENSE),
this repository is free and open source software.

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].


[distribution packages]: https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#distribution-package-vs-import-package
[uv]: https://docs.astral.sh/uv/
[pyproject.toml]: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
[in CI]: ./.github/workflows/release.yml
[gridworks-admin]: https://pypi.org/project/gridworks-admin/
[gridworks-scada-protocol]: https://pypi.org/project/gridworks-scada-protocol/
[install uv]: https://docs.astral.sh/uv/getting-started/installation/#standalone-installer
[admin pyproject.toml]: ./packages/gridworks-admin/pyproject.toml
[uv version]: https://docs.astral.sh/uv/guides/package/#updating-your-version
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
## Local Demo setup

Follow the directions below for creating a dev environment (assumes mac or Pi).

In one terminal window:

```
cd spaceheat
python run_local.py
```

WE NEED A BETTER LOCAL DEV DEMO


## Creating a Dev environment for macos or Pi


 - Use python 3.10.6
- .gitignore includes gw_spaceheat/venv for virtualenv so from gw_spaceheat directory:
  - `python -m venv venv`  
  - `source venv/bin/activate`
  - `pip install -r requirements/dev.txt`

Run the tests from the root directory of the repo with:

    pytest

A hardware layout file is necessary to run the scada locally. Find the default path the layout file with: 
    
    python -c "import config; print(config.Paths().hardware_layout)"

For initial experiments the test layout file can be used. The test layout file is located at:
    
    tests/config/hardware-layout.json

Display the hardware layout with:
    
    python gw_spaceheat/show_layout.py

Display current settings with: 
    
    python gw_spaceheat/show_settings.py

There are some scratch notes on Pi-related setup (like enabling interfaces) in docs/pi_setup.md

### Adding libraries 
- If you are going to add libraries, install pip-tools to your venv:
  - `python -m pip install pip-tools`
  - If you want to add a new library used in all contexts, then go to gw_spaceheat/requirements, add it to base.in and run
      - `pip-compile --output-file=base.txt base.in`
      - `pip-compile --output-file=dev.txt dev.in`
      - `pip-compile --output-file=drivers.txt drivers.in`

The `.in` files clarify the key modules (including which ones are important to pin and which ones can be set to the latest release) and then the corresponding `.txt` files are generated via pip-tools. This means we always run on pinned requirements (from the .txt files) and can typically upgrade to the latest release, except for cases where the code requires a pinned older version.

The pip-tools also allow for building layers of requirements on top of each other. This allows us to have development tools that are not needed in production to show up for the first time in `dev.txt`, for example (like the pip-tool itself).

### Handling secrets and config variables
    
SETTING UP SECRETS.
Configuration variables (secret or otherwise) use dotenv module in a gitignored `.env` file, copied over from `.env-template`. These are accessed via `config.ScadaSettings`.


### Setting up MQTT

See instructions [here](https://gridworks-proactor.readthedocs.io/en/latest/#mosquitto) to set up a local MQTT broker
using [Mosquitto](https://mosquitto.org/).


### Static analsyis with ruff

[Ruff](https://docs.astral.sh/ruff/) is installed via the test and dev requirements. 
You can run it with:

```
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
python gw_spaceheat/run_scada.py --dry-run  
```

This command will will start the scada locally: 
```shell
python gw_spaceheat/run_scada.py 
```

These commands will start the local test ATN:
```shell
python tests/atn/run.py
```

## Dev cycle

Default branch is dev. Make PRs to this branch for review from your code branch. Make bug changes directly to this branch.


The main branch is protected - requires a pull request. Default pattern is PRs from dev to main.
This will also publish a new gwsproto package.

## License

Distributed under the terms of the [MIT license][license],
this repository is free and open source software.

## Contributing

Contributions are very welcome.
To learn more, see the [Contributor Guide].


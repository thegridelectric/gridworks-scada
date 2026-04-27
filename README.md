# GridWorks SCADA

[![Tests](https://github.com/thegridelectric/gridworks-scada/actions/workflows/ci.yaml/badge.svg)][tests]
[![Codecov](https://codecov.io/gh/thegridelectric/gridworks-scada/branch/main/graph/badge.svg)][codecov]

[tests]: https://github.com/thegridelectric/gridworks-scada/actions/workflows/ci.yaml
[codecov]: https://app.codecov.io/gh/thegridelectric/gridworks-scada
========


This repository is for GridWorks contributors developing SCADA software for transactive heat pump thermal storage systems.

The software runs residential heat-pump-based space-heating systems with thermal storage and coordinates operation with electric grid conditions. In practice, that means shifting energy use toward lower-cost or grid-favorable times while maintaining occupant comfort.

This repository is part of a larger GridWorks framework. It typically operates alongside a cloud-based actor called the **LeafTransactiveNode**, which provides higher-level dispatch and coordination. Internally, the code follows an actor-based architecture: many focused components communicate through messages, with each actor responsible for a limited operational domain.

This project is funded by Efficiency Maine.


## Quick Start


For most contributors:

1. **Start with the Testing section.** For many small changes, running tests locally is enough.
2. **Run SCADA locally with `.env` if needed.** This is useful when debugging runtime behavior or configuration issues.
3. **Use RabbitMQ only for integration scenarios.** This is typically needed when simulating upstream GridWorks/cloud behavior or multi-process local environments.

## Testing


  1. **Start the local test mosquitto broker** Run from the repo root:

    mosquitto -c tests/config/local_mosquitto.conf -v &

> If you already run Mosquitto through Homebrew as a background service, stop that first so ports are not already in use.

 2. **Create venv**: Run `./tools/mkenv.sh`.  This creates `gw_spaceheat/venv/`
    - (On a Raspberry Pi use `./tools/mkenv-pi.sh`.)
 3.  **Activate venv**:  `source gw_spaceheat/venv/bin/activate`
 4. **Run tests:** `pytest -v`

### Test Environment Notes

Although the larger GridWorks ecosystem uses message-passing through a RabbitMQ broker, **SCADA-only development and pytest runs do not require RabbitMQ**.

The SCADA process conceptually talks to two MQTT brokers:

- **upstream / gridworks_mqtt** — normally the cloud-side GridWorks broker
- **local / local_mqtt** — the LAN-side broker used for local actors such as SCADA2

For local testing, both are replaced with a simple cleartext Mosquitto setup.

Tests assume a local MQTT broker with an **upstream broker** at `localhost:1883`
and a **local/downstream broker** at `localhost:18831`.

### Optional Shell Alias

```
    alias gw="source $HOME/Coding/gridworks-scada/gw_spaceheat/venv/bin/activate \
    && cd $HOME/Coding/gridworks-scada \
    && export PYTHONPATH=$HOME/Coding/gridworks-scada/gw_spaceheat:$PYTHONPATH"
```
### Test Bootstrap Behavior

`pytest` automatically uses repo-owned local defaults from:

- `tests/config/.env-local`
- `tests/config/hardware-layout.json`

Your normal `.env` file is **not** used during pytest unless a specific test explicitly opts into it.

### CI Testing

The CI workflow uses a different broker/certificate setup in
[`.github/workflows/ci.yaml`](.github/workflows/ci.yaml). It uses a separate broker/certificate setup and exercises TLS paths.

If you need to understand or regenerate the test CA, broker certs, or client certs,
look at the [`gridworks-cert`](https://github.com/thegridelectric/gridworks-cert/README.md) repo first. This
repository relies on `gwcert` conventions and test CA paths from that toolchain.


## CLI

SCADA includes a lightweight command-line tool called `gws` that is useful for both development and production tasks.

### Install the CLI


    ./tools/install-gws.sh

### Common Commands

Show the current resolved configuration:

    gws config

This is often the fastest way to verify paths, environment variables, and active settings. For example:

    hardware_layout=PosixPath('[HOME]/.config/gridworks/scada/hardware-layout.json')

Preview what SCADA would do without starting it:

    gws run --dry-run

Start SCADA locally:

    gws run



### Practical Use

During development, `gws config` and `gws run --dry-run` are especially useful for confirming that your hardware layout, `.env`, and local broker settings are being picked up correctly.

## Running SCADA Locally with `.env`

Scada is designed to operate with a `.env` variable and a hardware layout.  You
may choose to use these while running locally. Be aware that they are NOT used in tests.


For development purposes I recommend updating the hardware layout location in your local `.env` file. To do this for the first time , **copy the existing `.env-template` over to `.env`. Then rerun `gws config` and confirm that the  layout is now `tests/config/hardware-layout.json`.


### Creating your own dev hardware layout
  
In a sibling directory clone the [tlayouts](https://github.com/thegridelectric/tlayouts) directory. Then: 

 - While in the virtual env for this repository, navigate to `tlayouts`.
 - Run `gen_orange.py`

This will generate a simulated hardware layout in `outputs/orange.generated.json` 
 - Update your `.env` to include:

```
SCADA_PATHS__HARDWARE_LAYOUT="../tlayouts/output/orange.generated.json"
LTN_PATHS__HARDWARE_LAYOUT="../tlayouts/output/orange.generated.json"
```

### Dependencies

Add package requirements in:

- `gw_spaceheat/requirements/dev.in` — development / CI
- `gw_spaceheat/requirements/drivers.in` — Raspberry Pi only
- `gw_spaceheat/requirements/base.in` — all environments

Then run:

    tools/pipc.sh

## Advanced: Using RabbitMQ for Multi-Repo Integration

If you want to do cross-repo tests you may want to use the dev rabbit broker  at   [https://github.com/thegridelectric/gridworks-base?tab=readme-ov-file#dev-rabbit-broker](https://github.com/thegridelectric/gridworks-base?tab=readme-ov-file#dev-rabbit-broker).  Follow instructions there. 

RabbitMQ must expose its MQTT plugin so SCADA can connect using MQTT. Three steps for getting the docker rabbit instance to enable mqtt:
```
docker exec -it gw-dev-rabbit rabbitmq-plugins enable rabbitmq_mqtt
docker exec -it gw-dev-rabbit rabbitmqctl restart_app
docker exec -it gw-dev-rabbit rabbitmq-plugins list
```

And confirm:
 [E*] rabbitmq_mqtt                     3.9.13

(Troubleshooting how to get this into the docker yaml file over in gridworks-base)

Test mqtt access via mqtt_sub:

```
mosquitto_sub -h localhost -p 1885 -u smqPublic -P smqPublic -t "#" -v
```

Should see an `mqtt-subscription-XXX` show up on the rabbit admin panel http://localhost:15672/#/queues.


### Linting

Run:

```shell
ruff check
```

Ruff is advisory today and does not yet pass.




## Admin

Install:

    uv tool install gridworks-admin

Update: 

    uv tool update gridworks-admin

Run locally:

    gwa watch


See the [packages directory README.md](./packages/README.md) for more information.



## Raspberry Pi Service

Install:

    ./service/install

Status:

    gwstatus

Start:

    gwstart

Pause:

    gwpause

Stop:

    gwstop


## Additional Documentation

For deployment, TLS, and editor setup details, see:

- `docs/tls.md`
- `docs/provisioning.md`
- `docs/editor-setup.md`

## License

Distributed under the terms of the [MIT license](./LICENSE),
this repository is free and open source software.

# Provisioning a SCADA Node

This guide covers preparing a new Raspberry Pi (or replacement device) to operate as a real GridWorks SCADA.

Use this document when bringing a site online, replacing failed hardware, or re-provisioning an existing installation.

This guide is **not** for local development or pytest. For those workflows, use the main README.

---
## 1. Make SD card

TODO: ADD

## 2. Install the SCADA Repository

Choose an installation location such as:

    ~/gridworks-scada

Clone the repository and enter it:

    git clone <repo-url>
    cd gridworks-scada

Create the Python environment:

    ./tools/mkenv-pi.sh

Activate it if needed:

    source gw_spaceheat/venv/bin/activate

Install the CLI:

    ./tools/install-gws.sh

---

## 3. Assign GNode and make Layout

Every deployed SCADA should correspond to a known GridWorks GNode

That identity will affect:

- certificates
- hardware layout
- broker authorization
- naming inside logs and telemetry

Confirm which site this unit is intended to become before continuing.

---

## 4. Retrieve Production Credentials

Production MQTT credentials and certificates are typically installed using:

    python gw_spaceheat/getkeys.py --help

This tool is used to place the required credentials in the expected filesystem locations.

Typical prerequisites include:

- SSH access for certificate retrieval
- configured `rclone`
- knowledge of the target site identity
- operational access permissions

If this process fails, coordinate with whoever manages deployment credentials.

---

## 5. Configure Local Environment

Create or update the local environment file if required:

    cp .env-template .env

Make sure all heater-specific `.env` variables are set correctly,
Use the correct broker endpoints

```
SCADA_GRIDWORKS_MQTT__HOST = "hw1-1.electricity.works"
SCADA_GRIDWORKS_MQTT__USERNAME = "smqPublic"
SCADA_GRIDWORKS_MQTT__PASSWORD = "GET PASSWD"
```

- logging preferences
- broker endpoints
- deployment-specific overrides

To inspect the resolved configuration:

    gws config

This is often the fastest way to verify active settings.

---

## 6. Hardware Layout

Confirm the correct hardware layout file is present.

Typical location:

    ~/.config/gridworks/scada/hardware-layout.json

To inspect the loaded layout:

    gws layout show

If replacing an existing node, ensure the correct site layout is restored before startup.

---

## 7. Install as a Service

Install the systemd services:

    ./service/install

Check status:

    gwstatus

Start services:

    gwstart

Pause the main service temporarily:

    gwpause

Stop services:

    gwstop

---

## 8. First Boot Validation

After starting the service, verify:

- service is running
- no restart loop
- upstream broker connection succeeds
- expected actors initialize
- sensors/components appear healthy
- logs do not show repeated certificate or config errors

Useful commands:

    gwstatus

and:

    journalctl -u gwspaceheat.service -f

(service name may vary by deployment)

---

## 9. Connectivity Checks

If the node does not connect upstream, check:

- internet access
- DNS resolution
- firewall restrictions
- system clock correctness
- certificate validity
- correct site identity
- broker hostname in config

Incorrect system time can break TLS.

---

## 10. Replacing a Failed Raspberry Pi

Typical replacement process:

1. Prepare new Pi
2. Install repo
3. Restore correct hardware layout
4. Reinstall credentials for the same site identity
5. Install/start service
6. Validate telemetry and controls

Be careful not to provision two live devices with the same identity unless intentionally coordinated.

---

## 11. Safe Bring-Up Recommendations

When possible:

- start with pumps/loads electrically safe
- verify sensors first
- verify relay outputs carefully
- observe logs during first runtime
- confirm expected control behavior before leaving site unattended

---

## 12. Troubleshooting

### Service Restarts Repeatedly

Usually caused by:

- bad `.env`
- missing hardware layout
- Python environment problems
- missing credentials

### Broker Authentication Failure

Usually caused by:

- wrong certs
- expired certs
- hostname mismatch
- wrong site identity

### Hardware Missing

Check:

- USB connections
- I2C enabled
- permissions
- wiring
- expected component IDs

### Wrong Site Appears in Logs

Likely wrong credentials, wrong config, or reused files from another deployment.

---

## 13. Operational Notes

After provisioning, future maintenance is usually:

- pull latest code
- restart service
- rotate credentials when needed
- update hardware layout after physical changes

---

## Related Documents

- `README.md` — local development and testing
- `docs/tls.md` — certificate and TLS details
- `docs/editor-setup.md` — contributor editor tooling
# TLS and Certificates

GridWorks supports TLS-secured MQTT communication for CI, integration testing, and production deployments.

For most local SCADA development and normal `pytest` runs, TLS is **not required**. Local tests default to the cleartext broker configuration described in the main README.

---

## Start Here: `gridworks-cert`

Certificate generation, local certificate authorities, and related tooling are maintained in the sibling repository:

[gridworks-cert]((https://github.com/thegridelectric/gridworks-cert/README.md))

If you need to create or troubleshoot certificates, begin there first.

That repository is the source of truth for:

- local Certificate Authority setup
- broker certificates
- client certificates
- `gwcert` usage
- certificate directory conventions

---

## When TLS Is Typically Needed

Use TLS when working on:

- CI certificate paths
- broker authentication behavior
- production-like local integration testing
- Raspberry Pi deployments using secured MQTT
- real GridWorks broker connectivity

For standard unit tests and most local SCADA-only work, use the non-TLS local broker setup instead.

---

## Local Certificate Workflow (Example)

Typical workflow:

1. Create or initialize the local CA in `gridworks-cert`
2. Generate broker certificates
3. Generate client certificates for SCADA / LTN
4. Configure broker TLS listeners
5. Point `.env` or runtime settings at the generated cert paths

Exact commands may evolve, so refer to `gridworks-cert` documentation first.

---

## Example: Test LTN Certificate

    gwcert key add --certs-dir $HOME/.config/gridworks/ltn/certs scada_mqtt
    cp $HOME/.local/share/gridworks/ca/ca.crt \
       $HOME/.config/gridworks/ltn/certs/scada_mqtt

## Example: Test SCADA Certificate

    gwcert key add --certs-dir $HOME/.config/gridworks/scada/certs gridworks_mqtt
    cp $HOME/.local/share/gridworks/ca/ca.crt \
       $HOME/.config/gridworks/scada/certs/gridworks_mqtt

---

## Example TLS Smoke Test

Subscriber:

    mosquitto_sub -h localhost -p 8883 -t foo \
      --cafile $HOME/.config/gridworks/ltn/certs/scada_mqtt/ca.crt \
      --cert $HOME/.config/gridworks/ltn/certs/scada_mqtt/scada_mqtt.crt \
      --key $HOME/.config/gridworks/ltn/certs/scada_mqtt/private/scada_mqtt.pem

Publisher:

    mosquitto_pub -h localhost -p 8883 -t foo -m '{"bar":1}' \
      --cafile $HOME/.config/gridworks/scada/certs/gridworks_mqtt/ca.crt \
      --cert $HOME/.config/gridworks/scada/certs/gridworks_mqtt/gridworks_mqtt.crt \
      --key $HOME/.config/gridworks/scada/certs/gridworks_mqtt/private/gridworks_mqtt.pem

If TLS is working, the subscriber should receive:

    {"bar":1}

---

## Production Credential Provisioning

For provisioning keys used with the real GridWorks broker, see:

    gw_spaceheat/getkeys.py --help

This typically requires:

- access credentials
- remote file sync tooling (such as rclone)
- target device connectivity
- correct broker identity / deployment inputs

---

## Troubleshooting

### TLS Handshake Errors

Usually caused by:

- wrong CA file
- hostname mismatch
- expired certificates
- incorrect key/cert pairing

### Local Tests Suddenly Expect TLS

Check whether your `.env` or shell environment is overriding the repo test defaults.

### Unsure Where to Begin

Go back to **gridworks-cert** first.
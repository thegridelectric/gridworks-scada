from actors.relay import Relay
from plant import Plant
from relay_drives import I2cRelayDrive, resolve_i2c_actuation
from scada_app import ScadaApp


def relay_on_bus(app: ScadaApp, relay_name: str) -> Relay:
    """A relay of a simulated board driven as a real board's is: through the
    bus actor, onto the bus's fake chips. The app itself puts the plant link
    behind a simulated board's relays, which has no expander to fail."""
    node = app.hardware_layout.node(relay_name)
    assert node is not None
    app._plant = Plant()
    app.plant.route_relay(
        relay_name, I2cRelayDrive(resolve_i2c_actuation(app.hardware_layout, node))
    )
    return Relay(relay_name, app)

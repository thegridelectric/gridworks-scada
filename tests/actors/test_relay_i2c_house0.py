"""House0 relays ride the same one I2C actuation path as Nolan's: each relay
is a thin component against the Krida board record, the board component
carries the field-chosen PCF8575 addresses, and the bus actor drives the
register-less port word. The panel is active-low, so an energize command
drives the pin to 0. The sim pair boots the sim Krida board (SimI2c with
SimPcf8575 ports); the real pair proves the same resolution against the
real record without silicon."""

import time
import uuid
from pathlib import Path

import pytest

from actors.i2c_bus import I2cBus
from actors.relay import I2cCommand, Relay, UNKNOWN_STATE
from drivers.sim_i2c import SimI2c
from gwproto.message import Message
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ChangeRelayPin, I2cExpanderType, RelayClosedOrOpen
from gwsproto.named_types import FsmFullReport, I2cResult
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


def make_app(pair: str) -> ScadaApp:
    layout, ops = PAIRS[pair]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    return make_app(request.param)


@pytest.fixture
def sim_rig() -> tuple[Relay, I2cBus]:
    scada_app = make_app("house0-sim")
    relay = Relay(H0N.vdc_relay, scada_app)
    bus = I2cBus(relay._i2c.bus_node.name, scada_app)
    relay.sent = []

    def relay_send(dst, payload, src=None):
        if dst.name == bus.name:
            bus.process_message(Message(Src=relay.name, Dst=bus.name, Payload=payload))
        else:
            relay.sent.append((dst.name, payload))

    def bus_send(dst, payload, src=None):
        if isinstance(payload, I2cResult) and dst.name == relay.name:
            relay.process_message(
                Message(Src=bus.name, Dst=relay.name, Payload=payload)
            )

    relay._send_to = relay_send
    bus._send_to = bus_send
    return relay, bus


def command(relay: Relay, *, energize: bool) -> I2cCommand:
    cfg = relay.relay_actor_config
    return I2cCommand(
        pin_value=1 if energize else 0,
        target_state=cfg.EnergizedState if energize else cfg.DeEnergizedState,
        event_name=cfg.EnergizingEvent if energize else cfg.DeEnergizingEvent,
        relay_pin_event=(
            ChangeRelayPin.Energize if energize else ChangeRelayPin.DeEnergize
        ),
        trigger_id=str(uuid.uuid4()),
        boss=relay.primary_scada,
        send_time_ms=int(time.time() * 1000),
    )


def port_level(relay: Relay, bus: I2cBus) -> int:
    a = relay._i2c
    port = bus.i2c.pcf8575s[a.i2c_address].read_bytes(2)
    return (port[a.output_register] >> a.bit_index) & 1


def test_every_house0_relay_resolves_against_the_krida_record(app: ScadaApp) -> None:
    layout = app.hardware_layout
    board = layout.scada_board()
    addresses = board.gt.I2cAddressList
    assert addresses == [0x20, 0x21]
    relays = [
        Relay(n.name, app) for n in layout.nodes.values() if n.ActorClass == "Relay"
    ]
    assert len(relays) == 13
    for relay in relays:
        a = relay._i2c
        assert a is not None, relay.name
        assert a.expander_type == I2cExpanderType.Pcf8575
        assert a.config_register is None
        assert a.input_register == a.output_register
        assert a.energized_level == 0
        assert not a.supports_readback
        marking = int(relay._component.gt.RelayName.removeprefix("Relay"))
        assert a.i2c_address == addresses[(marking - 1) // 16]
    by_name = {r.name: r for r in relays}
    assert by_name[H0N.vdc_relay]._i2c.i2c_address == 0x20
    assert by_name["zone1-main-failsafe-relay"]._i2c.i2c_address == 0x21  # Relay17


def test_bus_backend_is_pcf8575_only_on_the_sim_pair() -> None:
    bus = I2cBus("i2c-bus", make_app("house0-sim"))
    assert isinstance(bus.i2c, SimI2c)
    assert bus._expander_types == {
        0x20: I2cExpanderType.Pcf8575,
        0x21: I2cExpanderType.Pcf8575,
    }
    assert bus._expander_addresses == ()  # no TCA9555 init or reset guard
    assert set(bus.i2c.pcf8575s) == {0x20, 0x21}
    assert bus.i2c.expanders == {}


@pytest.mark.asyncio
async def test_house0_relay_energizes_low_and_reports(sim_rig) -> None:
    relay, bus = sim_rig
    await relay._boot_adopt()  # no readback: ready at once, state unknown
    assert relay.state == UNKNOWN_STATE
    assert port_level(relay, bus) == 1  # power-on: every pin high, all off
    cmd = command(relay, energize=True)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == RelayClosedOrOpen.RelayOpen  # vdc-relay is NC
    assert port_level(relay, bus) == 0
    assert relay._i2c_command is None
    reports = [p for _, p in relay.sent if isinstance(p, FsmFullReport)]
    assert [r.TriggerId for r in reports] == [cmd.trigger_id]
    cmd = command(relay, energize=False)
    relay._i2c_command = cmd
    await relay._attempt_command(cmd)
    assert relay.state == RelayClosedOrOpen.RelayClosed
    assert port_level(relay, bus) == 1
    # the other fifteen pins on the port are untouched by the read-modify-write
    a = relay._i2c
    port = bus.i2c.pcf8575s[a.i2c_address].read_bytes(2)
    assert port == [0xFF, 0xFF]

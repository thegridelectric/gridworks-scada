"""House0 local control on a gw.house0.no.sieg plant: which machine the
loader selects, and relay initialization on a layout with no Siegenthaler
loop, where the relays hp-boss owns are left to hp-boss."""

from pathlib import Path

from actors.local_control.house0.buffer_only_tou import BufferOnlyTouLocalControl
from actors.local_control_loader import LocalControl
from gwsproto.enums import ChangeRelayState, SeasonalStorageMode, ServiceMode
from gwsproto.named_types import ActuatorsReady, FsmEvent
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp
from tests.utils.scada_live_test_helper import ops_word_with

LC_NAME = CoreNodeNames.local_control
CONFIG = Path(__file__).parent.parent / "config"
HAZEL_LAYOUT = CONFIG / "gw.house0.no.sieg.hazel.layout.json"
HAZEL_OPS = CONFIG / "gw.house0.no.sieg.hazel.operational.params.json"


def buffer_only_machine(tmp_path: Path) -> BufferOnlyTouLocalControl:
    """The hazel pair authored BufferOnly heating, as elm runs, its local
    control's sends captured."""
    ops = ops_word_with(
        HAZEL_OPS,
        tmp_path / HAZEL_OPS.name,
        service_mode=ServiceMode.Heating,
        seasonal_storage_mode=SeasonalStorageMode.BufferOnly,
    )
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = HAZEL_LAYOUT
    settings.paths.operational_params = ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    lc = LocalControl(LC_NAME, scada_app)
    assert isinstance(lc._impl, BufferOnlyTouLocalControl)
    inner = lc._impl
    inner.sent = []
    inner._send_to = lambda dst, payload, src=None: inner.sent.append((dst.name, payload))
    return inner


def relay_commands(actor: BufferOnlyTouLocalControl) -> dict[str, str]:
    return {
        dst: p.EventName
        for dst, p in actor.sent
        if isinstance(p, FsmEvent) and p.EventType == ChangeRelayState.enum_name()
    }


def test_no_sieg_buffer_only_initializes_relays(tmp_path: Path) -> None:
    """On a no-sieg plant, relay initialization completes: the relays under
    the normal node are de-energized, and the relays the layout fixes under
    hp-boss (the call relay, the pump relay and its hack relay) get no
    command from local control."""
    lc = buffer_only_machine(tmp_path)
    lc.process_actuators_ready(lc.layout.node(CoreNodeNames.primary_scada), ActuatorsReady())
    assert lc.actuators_initialized
    commands = relay_commands(lc)
    assert commands, "local control de-energizes the relays it owns at init"
    for owner, relays in lc.layout.fixed_subtrees:
        for relay in relays:
            assert relay.name not in commands, f"{relay.name} belongs to {owner.name}"
    assert HSNN.secondary_pump_relay not in commands
    assert House0NodeNames.secondary_pump_hack_relay not in commands

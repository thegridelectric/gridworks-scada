"""The pump doctors restore the 0-10V power-on levels when they finish,
under local control on both sim House0 pairs. Local control's own node is
`lc` while the outputs report to `n`, so the restore has to address the
host's command node, not the host. The dist-pump monitor and doctor reach
every zone-call circuit, including one whose place differs from its zone's
(the sim Nolan living room's second circuit)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import ActorClass
from gwsproto.named_types import AnalogDispatch, DispatchAck, Glitch, ZoneCallCircuit
from gwsproto.names.core.node_names import CoreNodeNames

from actors.procedural.dist_pump_doctor import DistPumpDoctor
from actors.procedural.dist_pump_monitor import DistPumpMonitor
from actors.procedural.store_pump_doctor import StorePumpDoctor
from actors.zero_ten_outputer import code_from_volts_times_ten
from scada_app import ScadaApp
from sema_to_dc import zero_ten_power_on_volts_times_ten

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}


@pytest.fixture(params=sorted(PAIRS))
def host(request: pytest.FixtureRequest):
    """Local control's implementation, booted in-process; sends captured,
    waits skipped."""
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    h = app.get_communicator(CoreNodeNames.local_control)._impl
    h.sent = []
    h._send_to = lambda dst, payload, src=None: h.sent.append((dst.name, payload))

    async def no_wait(total_seconds: float, pat_every: float = 20.0) -> None:
        return None

    h.await_with_watchdog = no_wait
    return h


def restores_after(h, sent_before: int) -> dict[str, AnalogDispatch]:
    outputs = {a.Name for a in h.layout.actuators if a.ActorClass == ActorClass.ZeroTenOutputer}
    return {
        dst: p
        for dst, p in h.sent[sent_before:]
        if isinstance(p, AnalogDispatch) and dst in outputs
    }


@pytest.mark.parametrize("doctor_cls, flow_wait", [
    (DistPumpDoctor, "wait_for_dist_flow"),
    (StorePumpDoctor, "wait_for_store_flow"),
])
def test_doctor_restores_010_defaults_from_command_node(host, doctor_cls, flow_wait) -> None:
    doctor = doctor_cls(host=host)

    async def flow_seen(*args, **kwargs) -> bool:
        return True

    setattr(doctor, flow_wait, flow_seen)
    h = host
    assert h.command_node.handle == "auto.lc.n"
    assert h.node.handle == "auto.lc"
    before = len(h.sent)
    asyncio.run(doctor.run())
    restored = restores_after(h, before)
    outputs = [a for a in h.layout.actuators if a.ActorClass == ActorClass.ZeroTenOutputer]
    assert set(restored) == {o.Name for o in outputs}
    for o in outputs:
        p = restored[o.Name]
        assert p.FromHandle == "auto.lc.n"
        assert p.ToHandle == f"auto.lc.n.{o.Name}"
        assert p.Value == zero_ten_power_on_volts_times_ten(h.ops, o.Name)


def test_set_010_defaults_from_the_host_itself_sends_nothing(host) -> None:
    """The bug the doctors had: local control's own node is not the
    outputs' boss, so the no-argument call finds no direct reports."""
    h = host
    before = len(h.sent)
    h.set_010_defaults()
    assert restores_after(h, before) == {}


@pytest.mark.parametrize("doctor_cls, flow_wait, pump", [
    (DistPumpDoctor, "wait_for_dist_flow", "dist"),
    (StorePumpDoctor, "wait_for_store_flow", "store"),
])
def test_doctor_zeroes_its_010v_through_the_command_tree(host, doctor_cls, flow_wait, pump) -> None:
    """The doctor's first move is the pump's 0-10 V output to zero. Delivered
    the way the proactor delivers an in-process message (the scada's router),
    that dispatch has to reach the output and be taken: the scada's own
    handler raises on a payload it does not expect and the proactor stops
    (elm, 2026-10-28 04:15 ET, eight boots in a row), and the output drops
    a dispatch whose wire source is not its FromHandle. Relay events and
    glitches stay captured: a relay's reply needs a running proactor."""
    h = host
    scada = h.services.prime_actor
    out = h.services.get_communicator(getattr(h, f"{pump}_010v").name)
    out_sent: list = []
    out._send_to = lambda dst, payload, src=None: out_sent.append((dst.name, payload))
    scada_failures: list = []

    def route(dst: ShNode, payload, src: ShNode | None = None) -> None:
        if isinstance(payload, AnalogDispatch) or dst.name == scada.name:
            try:
                scada._send_to(dst, payload, h.node if src is None else src)
            except Exception as e:  # noqa: BLE001
                scada_failures.append((dst.name, type(payload).__name__, repr(e)))
        else:
            h.sent.append((dst.name, payload))

    h._send_to = route
    levels: list[int] = []

    async def record_level(total_seconds: float, pat_every: float = 20.0) -> None:
        levels.append(out.target_code)

    h.await_with_watchdog = record_level
    doctor = doctor_cls(host=h)

    async def flow_seen(*args, **kwargs) -> bool:
        return True

    setattr(doctor, flow_wait, flow_seen)
    asyncio.run(doctor.run())
    assert scada_failures == []
    assert [p.Summary for _, p in out_sent if isinstance(p, Glitch)] == []
    assert levels[0] == code_from_volts_times_ten(0, out.facts)
    assert out.target_code == out.power_on_code
    acks = [p for _, p in out_sent if isinstance(p, DispatchAck)]
    assert [a.ToHandle for a in acks] == [h.command_node.handle, h.command_node.handle]


# --- circuits are looked up, not named by position ---------------------------


FANCOIL = "living-rm-fancoil"  # circuit 5, serving zone 2 (living-rm)


@pytest.fixture
def nolan_layout() -> HydronicLayout:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app.hardware_layout


class CircuitHost:
    """A procedural host on a real layout that records the circuit each zone
    relay command names, in place of sending it."""

    def __init__(self, layout: HydronicLayout) -> None:
        self.layout = layout
        self.data = SimpleNamespace(latest_channel_values={})
        self.commands: list[tuple[str, str]] = []
        self.node = layout.node(CoreNodeNames.local_control)
        self.command_node = layout.node(CoreNodeNames.local_control_normal)
        self.ltn = self.node
        self.dist_010v = layout.node("secondary-010v")

    def log(self, note: str) -> None:
        pass

    def _send_to(self, dst: ShNode, payload, src: ShNode | None = None) -> None:
        pass

    async def await_with_watchdog(self, total_seconds: float, pat_every: float = 20.0) -> None:
        return None

    def set_010_defaults(self, command_node: ShNode | None = None) -> None:
        pass

    def set_010_level(self, dfr_node: ShNode, volts_times_ten: int, command_node: ShNode | None = None) -> None:
        pass

    def heatcall_ctrl_to_scada(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        self.commands.append(("to-scada", circuit.Name))

    def heatcall_ctrl_to_stat(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        self.commands.append(("to-stat", circuit.Name))

    def stat_ops_close_relay(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        self.commands.append(("ops-close", circuit.Name))

    def stat_ops_open_relay(self, circuit: ZoneCallCircuit, command_node: ShNode | None = None) -> None:
        self.commands.append(("ops-open", circuit.Name))


def test_heat_call_channel_is_the_circuits_own(nolan_layout: HydronicLayout) -> None:
    [fancoil] = [c for c in nolan_layout.hydronic.ZoneCallCircuits if c.Name == FANCOIL]
    assert nolan_layout.heat_call_channel(fancoil) == "zone5-living-rm-fancoil-heat-call"


def test_dist_pump_monitor_reads_a_call_on_a_circuit_away_from_its_zones_place(
    nolan_layout: HydronicLayout,
) -> None:
    """Only the fancoil calls. Its heat-call channel is named for place 5,
    which no zone index reaches."""
    host = CircuitHost(nolan_layout)
    for circuit in nolan_layout.hydronic.ZoneCallCircuits:
        host.data.latest_channel_values[nolan_layout.heat_call_channel(circuit)] = 0
    [fancoil] = [c for c in nolan_layout.hydronic.ZoneCallCircuits if c.Name == FANCOIL]
    host.data.latest_channel_values[nolan_layout.heat_call_channel(fancoil)] = 1
    monitor = DistPumpMonitor(host=host, doctor=DistPumpDoctor(host=host))
    assert monitor._any_zones_calling()


def test_dist_pump_doctor_commands_every_circuits_relays(nolan_layout: HydronicLayout) -> None:
    host = CircuitHost(nolan_layout)
    doctor = DistPumpDoctor(host=host)

    async def flow_seen(*args, **kwargs) -> bool:
        return True

    doctor.wait_for_dist_flow = flow_seen
    asyncio.run(doctor.run())
    names = [c.Name for c in nolan_layout.hydronic.ZoneCallCircuits]
    assert FANCOIL in names
    for command in ("to-scada", "ops-close", "to-stat", "ops-open"):
        assert [n for k, n in host.commands if k == command] == names

"""The pump doctors restore the 0-10V power-on levels when they finish,
under local control on both sim House0 pairs. Local control's own node is
`lc` while the outputs report to `n`, so the restore has to address the
host's command node, not the host."""

import asyncio
from pathlib import Path

import pytest
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ActorClass
from gwsproto.named_types import AnalogDispatch

from actors.procedural.dist_pump_doctor import DistPumpDoctor
from actors.procedural.store_pump_doctor import StorePumpDoctor
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
    h = app.get_communicator(H0N.local_control)._impl
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

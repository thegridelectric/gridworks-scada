"""Each control machine announces its own state when it starts.

The scada seeds only its own TopState row of `latest_machine_state`; the
LeafAlly and LocalControl rows come from the actors themselves, sent as a
`SingleMachineState` in `start()`, so the first snapshot carries every
machine's row and reports the machine's real enum (Standby local control
speaks `LocalControlStandbyTopState`, not `LocalControlTopState`).

Runs against both authored pairs: the pinned Nolan fixture and the House0
fixture."""

import asyncio
from pathlib import Path

import pytest

from actors.leaf_ally_loader import LeafAlly
from actors.local_control_loader import LocalControl
from gwsproto.named_types import SingleMachineState
from gwsproto.names.core.node_names import CoreNodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def capture_sends(actor) -> list:
    impl = actor._impl
    impl.sent = []
    impl._send_to = lambda dst, payload, src=None: impl.sent.append((dst.name, payload))
    return impl.sent


def start_and_collect(actor) -> list:
    """Run start() inside a loop (it may spawn keepalive tasks), then cancel
    whatever it spawned so nothing outlives the test."""
    sent = capture_sends(actor)

    async def run() -> None:
        actor.start()
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()

    asyncio.run(run())
    return sent


def announced(sent: list) -> SingleMachineState:
    assert sent, "start() announced nothing"
    dst, payload = sent[0]
    assert dst == CoreNodeNames.primary_scada
    assert isinstance(payload, SingleMachineState)
    return payload


def test_scada_seeds_only_its_own_row(app: ScadaApp) -> None:
    scada = app.scada
    assert set(scada.data.latest_machine_state) == {scada.name}


def test_leaf_ally_announces_its_state_on_start(app: ScadaApp) -> None:
    la = LeafAlly(CoreNodeNames.leaf_ally, app)
    sms = announced(start_and_collect(la))
    assert sms.MachineHandle == la.node.handle
    assert sms.StateEnum == type(la.state).enum_name()
    assert sms.State == la.state


def test_local_control_announces_its_state_on_start(app: ScadaApp) -> None:
    lc = LocalControl(CoreNodeNames.local_control, app)
    sms = announced(start_and_collect(lc))
    assert sms.MachineHandle == lc.node.handle
    assert sms.StateEnum == type(lc.top_state).enum_name()
    assert sms.State == lc.top_state

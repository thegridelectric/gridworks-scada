"""A GPIO relay on a simulated board has no pin to write, but its word to
its boss is unchanged: the state report and the fsm.full.report under
the command's TriggerId go out as on a real board. Without this the
pico-cycler, which waits for the relay's confirmation before closing it
again, never completes a cycle on a sim board."""

import time
import uuid
from pathlib import Path

import pytest

from actors.relay import Relay
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ChangeRelayPin, ChangeRelayState
from gwsproto.named_types import FsmEvent, FsmFullReport
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def test_sim_gpio_relay_reports_to_its_boss(app: ScadaApp) -> None:
    scada = app.scada
    vdc = scada.layout.vdc_relay
    relay = scada.get_communicator(vdc.name)
    assert isinstance(relay, Relay)
    assert relay.GPIO is None, "the fixture's board must be simulated"
    sent: list = []
    relay._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    cycler = scada.layout.node(H0N.pico_cycler)
    event = FsmEvent(
        FromHandle=cycler.handle,
        ToHandle=vdc.handle,
        EventType=ChangeRelayState.enum_name(),
        EventName=ChangeRelayState.OpenRelay,
        SendTimeUnixMs=int(time.time() * 1000),
        TriggerId=str(uuid.uuid4()),
    )

    relay._process_event_message(cycler.name, event)

    reports = [(dst, p) for dst, p in sent if isinstance(p, FsmFullReport)]
    assert len(reports) == 1
    dst, report = reports[0]
    assert dst == cycler.name
    assert report.TriggerId == event.TriggerId
    assert [a.Event for a in report.AtomicList] == [ChangeRelayState.OpenRelay, ChangeRelayPin.Energize]

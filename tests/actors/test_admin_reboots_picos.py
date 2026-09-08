"""End to end in process: gwadmin's client builds the reboot-picos dispatch
exactly as the button sends it, the scada's admin-dispatch routing hands
it to the pico-cycler by the last segment of ToHandle, and the cycler
opens vdc-relay under the command's own TriggerId. The loop's second
half (the relay cycling, sim picos dying and rebooting, the full report
journaled) is the dev-broker rung in the design spoke.

Runs over both sim fixtures."""

import asyncio
from pathlib import Path

import pytest

from actors.pico_cycler import PicoCycler
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ChangeRelayState,
    PicoCyclerEvent,
    PicoCyclerState,
    RebootPicos,
    TopState,
)
from gwsproto.named_types import AdminDispatch, FsmEvent
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0-sim": ("gw.house0.sim.layout.json", "gw.house0.sim.operational.params.json"),
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


class CapturingAdminClient:
    """Stands in for gwadmin's AdminClient: keeps what the relay client publishes."""

    def __init__(self) -> None:
        self.published: list = []

    def publish(self, payload) -> None:
        self.published.append(payload)

    def started(self) -> bool:
        return False


def gwadmin_reboot_dispatch(app: ScadaApp, timeout_seconds: int) -> AdminDispatch:
    """The pico-cycler row's action: the client learns the row from the
    scada's capabilities and sends RebootPicos in the row's own vocabulary."""
    admin = CapturingAdminClient()
    client = RelayWatchClient()
    client.set_admin_client(admin)
    client.process_scada_control_capabilities(app.scada.control_capabilities)
    client.send_command(H0N.pico_cycler, RebootPicos.RebootPicos, timeout_seconds)
    assert len(admin.published) == 1
    dispatch = admin.published[0]
    assert isinstance(dispatch, AdminDispatch)
    return dispatch


def test_gwadmin_dispatch_is_the_cycler_command(app: ScadaApp) -> None:
    dispatch = gwadmin_reboot_dispatch(app, 300)
    event = dispatch.DispatchTrigger
    assert dispatch.TimeoutSeconds == 300
    assert event.FromHandle == H0N.admin
    assert event.ToHandle == f"{H0N.admin}.{H0N.pico_cycler}"
    assert event.EventType == RebootPicos.enum_name()
    assert event.EventName == RebootPicos.RebootPicos


def test_admin_dispatch_reaches_cycler_and_opens_relay_under_its_trigger_id(app: ScadaApp) -> None:
    scada = app.scada
    sent_by_scada: list = []
    scada._send_to = lambda dst, payload, src=None: sent_by_scada.append((dst.name, payload))
    cycler = scada.get_communicator(H0N.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    sent_by_cycler: list = []
    cycler._send_to = lambda dst, payload, src=None: sent_by_cycler.append((dst.name, payload))
    dispatch = gwadmin_reboot_dispatch(app, 300)

    async def run() -> None:
        scada.process_admin_dispatch(scada.admin, dispatch)
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()

    asyncio.run(run())

    assert scada.top_state == TopState.Admin
    assert cycler.node.handle == f"{H0N.admin}.{H0N.pico_cycler}"
    assert cycler.state == PicoCyclerState.RelayOpening
    assert cycler.trigger_id == dispatch.DispatchTrigger.TriggerId
    assert [r.Event for r in cycler.fsm_reports] == [PicoCyclerEvent.ShakeZombies]
    opens = [p for dst, p in sent_by_cycler if isinstance(p, FsmEvent)]
    assert len(opens) == 1
    assert opens[0].ToHandle == scada.layout.vdc_relay.handle
    assert opens[0].EventName == ChangeRelayState.OpenRelay
    assert opens[0].TriggerId == dispatch.DispatchTrigger.TriggerId

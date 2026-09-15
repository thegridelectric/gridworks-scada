"""sieg-loop, the Siegenthaler valve actor on both House0 fixtures: a valve
movement reaches the two relays it drives (keep/send direction, then the
on/off that starts the motion), under the sieg-loop's own handle. Guards the
partition residue where the actor lost its choreography and the movement
error was swallowed, so the valve silently never moved."""

from pathlib import Path

import pytest

from actors.hydronic.house0 import House0Hydronic
from actors.sieg_loop import SiegLoop, SiegValveEvent, SiegValveState
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import ChangeKeepSend, ChangeRelayState
from gwsproto.named_types import FsmEvent
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
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


def sieg_loop_actor(app: ScadaApp) -> SiegLoop:
    actor = app.get_communicator_as_type(H0N.sieg_loop, SiegLoop)
    assert actor is not None, "sieg-loop is constructed in every House0 layout"
    return actor


def capture(actor: SiegLoop) -> list:
    sent: list = []
    actor._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


def test_sieg_loop_carries_the_valve_choreography(app: ScadaApp) -> None:
    actor = sieg_loop_actor(app)
    assert isinstance(actor, House0Hydronic)
    assert actor.hp_boss.name == HSNN.hp_boss


@pytest.mark.parametrize(
    ("valve_event", "direction"),
    [
        (SiegValveEvent.StartKeepingMore, ChangeKeepSend.ChangeToKeepMore),
        (SiegValveEvent.StartKeepingLess, ChangeKeepSend.ChangeToKeepLess),
    ],
)
def test_valve_movement_reaches_both_relays(
    app: ScadaApp, valve_event: SiegValveEvent, direction: ChangeKeepSend
) -> None:
    """A keep-more or keep-less movement sends the direction to the keep/send
    relay and then closes the on/off relay, both from the sieg-loop's handle
    (the relays sit under it in the command tree)."""
    actor = sieg_loop_actor(app)
    sent = capture(actor)
    start = (
        SiegValveState.FullySend
        if valve_event == SiegValveEvent.StartKeepingMore
        else SiegValveState.FullyKeep
    )
    actor.valve_state = start
    actor.trigger_valve_event(valve_event)

    assert [name for name, _ in sent] == [H0N.hp_loop_keep_send, H0N.hp_loop_on_off]
    keep_send, on_off = (payload for _, payload in sent)
    assert isinstance(keep_send, FsmEvent)
    assert keep_send.EventType == ChangeKeepSend.enum_name()
    assert keep_send.EventName == direction
    assert keep_send.FromHandle == actor.node.handle
    assert isinstance(on_off, FsmEvent)
    assert on_off.EventType == ChangeRelayState.enum_name()
    assert on_off.EventName == ChangeRelayState.CloseRelay
    assert on_off.FromHandle == actor.node.handle
    assert actor.valve_state != start

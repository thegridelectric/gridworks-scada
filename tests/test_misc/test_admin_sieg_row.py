"""The panel's sieg-loop row on a House0 scada offers the two commands the
valve can use from its observed state: at a stop, the move to the other
stop; in a steady blend, both moves; travelling, StopValve and the move to
the other stop, since the motor is already headed for this one. The
Action cell joins the pair with a bare slash so it fits its width."""

from pathlib import Path

import pytest

from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwsproto.enums import ActorClass, MoveSiegValve, SiegValveState
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def sieg() -> RelayWidgetConfig:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.willow.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.willow.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    node = next(n for n in scada_app.scada.layout.nodes.values() if n.ActorClass == ActorClass.SiegLoop)
    configs = RelayWatchClient._get_relay_configs(scada_app.scada.control_capabilities)
    return RelayWidgetConfig.from_config(configs[node.name])


def offered(config: RelayWidgetConfig, state: str) -> list[str]:
    return [c.event for c in config.offered_commands(state)]


def test_a_stop_offers_the_move_to_the_other_stop(sieg: RelayWidgetConfig) -> None:
    assert offered(sieg, SiegValveState.FullyKeep) == [MoveSiegValve.MoveToFullSend]
    assert offered(sieg, SiegValveState.FullySend) == [MoveSiegValve.MoveToFullKeep]
    assert sieg.offered_command(SiegValveState.FullyKeep, 1) is None


def test_a_steady_blend_offers_both_moves(sieg: RelayWidgetConfig) -> None:
    assert offered(sieg, SiegValveState.SteadyBlend) == [
        MoveSiegValve.MoveToFullSend,
        MoveSiegValve.MoveToFullKeep,
    ]


def test_travelling_offers_stop_and_the_other_stop(sieg: RelayWidgetConfig) -> None:
    assert offered(sieg, SiegValveState.KeepingMore) == [MoveSiegValve.MoveToFullSend, MoveSiegValve.StopValve]
    assert offered(sieg, SiegValveState.KeepingLess) == [MoveSiegValve.MoveToFullKeep, MoveSiegValve.StopValve]
    assert sieg.get_action_str(SiegValveState.KeepingMore) == "MoveToFullSend/StopValve"
    assert len(sieg.get_action_str(SiegValveState.KeepingLess)) <= 25

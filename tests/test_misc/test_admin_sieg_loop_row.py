"""The panel's sieg-loop row on a House0 scada: at a stop it offers the
move to the other stop; mid-travel, where the observed state is no
command's result, it offers both moves, so an operator can re-home or
reverse a valve that is moving. Relays 14 and 15, owned by the loop,
offer nothing."""

from pathlib import Path

import pytest

from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwsproto.enums import MoveSiegValve, RelayClosedOrOpen, SiegValveState
from gwsproto.names.house0.node_names import House0NodeNames
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def configs() -> dict[str, RelayWidgetConfig]:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.orange.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.orange.operational.params.json"
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return {
        name: RelayWidgetConfig.from_config(config)
        for name, config in RelayWatchClient._get_relay_configs(
            scada_app.scada.control_capabilities
        ).items()
    }


def offered(config: RelayWidgetConfig, state: str) -> list[str]:
    return [c.event for c in config.offered_commands(state)]


def test_sieg_loop_row_offers_the_other_stop_at_a_stop(configs: dict[str, RelayWidgetConfig]) -> None:
    loop = configs[House0NodeNames.sieg_loop]
    assert loop.state_type == SiegValveState.enum_name()
    assert offered(loop, SiegValveState.FullySend) == [MoveSiegValve.MoveToFullKeep]
    assert offered(loop, SiegValveState.FullyKeep) == [MoveSiegValve.MoveToFullSend]


def test_sieg_loop_row_offers_both_moves_while_moving(configs: dict[str, RelayWidgetConfig]) -> None:
    loop = configs[House0NodeNames.sieg_loop]
    for state in (SiegValveState.KeepingLess, SiegValveState.KeepingMore, SiegValveState.SteadyBlend):
        assert offered(loop, state) == [MoveSiegValve.MoveToFullSend, MoveSiegValve.MoveToFullKeep]
    assert loop.get_action_str(SiegValveState.SteadyBlend) == "MoveToFullSend / MoveToFullKeep"


def test_loop_relays_offer_nothing(configs: dict[str, RelayWidgetConfig]) -> None:
    for name in (House0NodeNames.hp_loop_on_off, House0NodeNames.hp_loop_keep_send):
        assert configs[name].commands == []
        assert offered(configs[name], RelayClosedOrOpen.RelayClosed) == []

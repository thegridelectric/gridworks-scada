"""The panel's secondary-pump row on a Nolan scada: the pump sits under
hp-boss and its interface says admin may take it, so the row offers the
relay's own events from its observed state like any zone relay, indented
under hp-boss. The call relay's row, owned with no such flag, offers
nothing; the hp-boss row is unchanged."""

from pathlib import Path

import pytest

from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwsproto.enums import ChangeRelayState, HpBossState, RelayClosedOrOpen, TurnHpOnOff
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture
def configs() -> dict[str, RelayWidgetConfig]:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.nolan.layout.json"
    settings.paths.operational_params = CONFIG / "gw.nolan.operational.params.json"
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


def test_pump_row_offers_the_relay_pair_under_hp_boss(configs: dict[str, RelayWidgetConfig]) -> None:
    pump = configs[HSNN.secondary_pump_relay]
    assert pump.owner == HSNN.hp_boss
    assert pump.state_type == RelayClosedOrOpen.enum_name()
    assert offered(pump, RelayClosedOrOpen.RelayOpen) == [ChangeRelayState.CloseRelay]
    assert offered(pump, RelayClosedOrOpen.RelayClosed) == [ChangeRelayState.OpenRelay]


def test_call_relay_row_offers_nothing(configs: dict[str, RelayWidgetConfig]) -> None:
    call = configs[HSNN.hp_scada_ops_relay]
    assert call.owner == HSNN.hp_boss
    assert call.commands == []
    assert offered(call, RelayClosedOrOpen.RelayOpen) == []


def test_hp_boss_row_is_unchanged(configs: dict[str, RelayWidgetConfig]) -> None:
    boss = configs[HSNN.hp_boss]
    assert offered(boss, HpBossState.HpOff) == [TurnHpOnOff.TurnOn]
    assert offered(boss, HpBossState.HpOn) == [TurnHpOnOff.TurnOff]

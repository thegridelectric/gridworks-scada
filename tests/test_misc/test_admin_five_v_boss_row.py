"""The panel's five-v-boss row on a Nolan scada offers every command its
two vocabularies allow from the observed state: the hold's TurnOff and
the forwarded RebootPicos at rest, TurnOn alone while the 5 V is held
off, and mid-transition the hold's way back with the reboot withheld
(the node nacks Busy either way; the panel does not pretend otherwise).
A relay row offers the one event that leads elsewhere; the cycler row,
commanded through five-v-boss, offers nothing."""

from pathlib import Path

import pytest

from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import FiveVBossState, RebootPicos, RelayClosedOrOpen, Turn5VOnOff
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


def offered(config: RelayWidgetConfig, state: str) -> list[tuple[str, str]]:
    return [(c.event_type, c.event) for c in config.offered_commands(state)]


def test_five_v_boss_offers_hold_and_reboot_at_rest(configs: dict[str, RelayWidgetConfig]) -> None:
    boss = configs[H0N.five_v_boss]
    assert offered(boss, FiveVBossState.PicoCycler) == [
        (Turn5VOnOff.enum_name(), Turn5VOnOff.TurnOff),
        (RebootPicos.enum_name(), RebootPicos.RebootPicos),
    ]
    assert boss.offered_command(FiveVBossState.PicoCycler, 0).event == Turn5VOnOff.TurnOff
    assert boss.offered_command(FiveVBossState.PicoCycler, 1).event == RebootPicos.RebootPicos
    assert boss.get_action_str(FiveVBossState.PicoCycler) == "TurnOff / RebootPicos"


def test_five_v_boss_offers_turn_on_alone_while_held_off(configs: dict[str, RelayWidgetConfig]) -> None:
    boss = configs[H0N.five_v_boss]
    assert offered(boss, FiveVBossState.FiveVOff) == [(Turn5VOnOff.enum_name(), Turn5VOnOff.TurnOn)]
    assert boss.offered_command(FiveVBossState.FiveVOff, 1) is None


def test_five_v_boss_withholds_reboot_mid_transition(configs: dict[str, RelayWidgetConfig]) -> None:
    boss = configs[H0N.five_v_boss]
    for state in (FiveVBossState.TurningOff, FiveVBossState.TurningOn):
        assert [event_type for event_type, _ in offered(boss, state)] == [Turn5VOnOff.enum_name()]
    assert offered(boss, None) == []
    assert boss.get_action_str(None) == ""


def test_relay_row_offers_the_other_state(configs: dict[str, RelayWidgetConfig]) -> None:
    relay = next(
        c for c in configs.values() if c.owner is None and c.state_type == RelayClosedOrOpen.enum_name()
    )
    [(_, event)] = offered(relay, RelayClosedOrOpen.RelayClosed)
    assert event == next(c.event for c in relay.commands if c.to_state == RelayClosedOrOpen.RelayOpen)
    assert len(offered(relay, RelayClosedOrOpen.RelayOpen)) == 1


def test_owned_rows_offer_nothing(configs: dict[str, RelayWidgetConfig]) -> None:
    for name in (H0N.pico_cycler, H0N.vdc_relay, H0N.hp_scada_ops_relay):
        assert configs[name].commands == []
        assert offered(configs[name], RelayClosedOrOpen.RelayClosed) == []

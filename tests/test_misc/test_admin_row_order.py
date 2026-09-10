"""The panel's rows on a Nolan scada: a relay owned by an interior command
node knows its owner from the capabilities' handles, and the table order
puts it directly under that owner's row."""

from pathlib import Path

import pytest

from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwadmin.watch.widgets.relay_widget_info import RelayWidgetConfig
from gwadmin.watch.widgets.relays import Relays
from gwsproto.data_classes.house_0_names import H0N
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


def test_owned_relays_sit_under_their_owner(app: ScadaApp) -> None:
    configs = RelayWatchClient._get_relay_configs(app.scada.control_capabilities)
    owners = {name: c.owner for name, c in configs.items() if c.owner is not None}
    assert owners == {
        H0N.pico_cycler: H0N.five_v_boss,
        H0N.vdc_relay: H0N.pico_cycler,
        H0N.hp_scada_ops_relay: H0N.hp_boss,
    }
    ordered = sorted(configs.values(), key=lambda c: Relays.row_order_key(c, configs))
    names = [c.about_node_name for c in ordered]
    assert names.index(H0N.pico_cycler) == names.index(H0N.five_v_boss) + 1
    assert names.index(H0N.vdc_relay) == names.index(H0N.pico_cycler) + 1
    assert names.index(H0N.hp_scada_ops_relay) == names.index(H0N.hp_boss) + 1
    unowned = [n for n in names if configs[n].owner is None]
    assert unowned == sorted(unowned)


def test_owned_rows_indent_one_step(app: ScadaApp) -> None:
    configs = RelayWatchClient._get_relay_configs(app.scada.control_capabilities)
    widget_configs = {n: RelayWidgetConfig.from_config(c) for n, c in configs.items()}
    assert Relays.row_name(widget_configs[H0N.five_v_boss]) == "Five V Boss"
    assert Relays.row_name(widget_configs[H0N.pico_cycler]) == "  Pico Cycler"
    assert Relays.row_name(widget_configs[H0N.vdc_relay]) == "  Vdc"
    assert Relays.row_name(widget_configs[H0N.hp_scada_ops_relay]) == "  Hp Scada Ops"

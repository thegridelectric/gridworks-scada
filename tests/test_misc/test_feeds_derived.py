"""One rule decides whether a device actor posts to the derived generator:
the layout says a DerivedChannel consumes one of its channels. Both sim
pairs carry sieg-flow feeding a derived flow and dist-flow feeding none."""

from pathlib import Path

import pytest
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN

from actors.sim_sensor import SimSensorActor
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
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_layout_says_which_channels_feed_a_derived_channel(app: ScadaApp) -> None:
    layout = app.scada.layout
    assert layout.feeds_derived([House0NodeNames.sieg_flow])
    assert not layout.feeds_derived([HSNN.dist_flow])
    assert layout.feeds_derived([HSNN.dist_flow, House0NodeNames.sieg_flow])
    assert not layout.feeds_derived([])


def test_a_channel_feeding_only_the_power_meters_own_derived_channel_does_not_feed(
    app: ScadaApp,
) -> None:
    layout = app.scada.layout
    transactive = next(
        dc for dc in layout.derived_channels.values() if dc.Strategy == "transactive-power"
    )
    assert transactive.CreatedByNodeName == layout.power_meter_node.name
    assert not layout.feeds_derived(transactive.InputChannelNames)
    assert layout.feeds_derived(["zone1-main-whitewire-pwr"])


def test_sim_sensors_take_the_rule_from_the_layout(app: ScadaApp) -> None:
    sieg = app.get_communicator_as_type(House0NodeNames.sieg_flow, SimSensorActor)
    dist = app.get_communicator_as_type(HSNN.dist_flow, SimSensorActor)
    assert sieg is not None and dist is not None
    assert sieg.feeds_derived
    assert not dist.feeds_derived

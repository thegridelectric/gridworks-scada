"""A layout's store tanks are read off the tank reader nodes it carries, so a
layout without water store tanks answers no tanks and the store-temperature
readers answer None instead of raising."""

from pathlib import Path

import pytest
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.helpers import store_tanks

from actors.derived_generator import DerivedGenerator
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"


def test_store_tanks_follow_the_reader_nodes() -> None:
    tanks = store_tanks({"buffer", "tank1", "tank2", "zone1-bedrooms", "tank7"})
    assert sorted(tanks) == [1, 2]
    assert tanks[2].depth3 == "tank2-depth3"
    assert store_tanks({"buffer", "hp-odu"}) == {}


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / "gw.house0.willow.layout.json"
    settings.paths.operational_params = CONFIG / "gw.house0.willow.operational.params.json"
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_hardware_layout_answers_its_tanks(app: ScadaApp) -> None:
    layout = app.scada.layout
    assert layout.has_store_tanks
    assert sorted(layout.store_tanks) == [1]
    assert "tank1-depth1-device" in layout.tank_device_temp_channels


def test_store_temps_are_none_without_tanks(app: ScadaApp) -> None:
    actor = app.get_communicator_as_type(CoreNodeNames.derived_generator, DerivedGenerator)
    assert actor is not None
    tank1 = actor.layout.store_tanks[1]
    actor.data.latest_channel_values[tank1.depth1] = 15_000
    actor.data.latest_channel_values[tank1.depth3] = 12_000
    assert actor.hottest_store_temp().f == pytest.approx(150.0, abs=0.1)
    assert actor.coldest_store_temp().f == pytest.approx(120.0, abs=0.1)

    actor.layout.store_tanks = {}
    assert not actor.layout.has_store_tanks
    assert actor.hottest_store_temp() is None
    assert actor.coldest_store_temp() is None

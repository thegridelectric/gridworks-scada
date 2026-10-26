"""LayoutLiteDc answers whether a layout has store tanks, and which, from the
layout itself: the tank reader nodes it carries, not a count. Every current
layout has tanks; a slab house with no water store tanks answers no."""

from pathlib import Path

import pytest
from gwsproto.data_classes.layout_lite_dc import LayoutLiteDc

from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
}


@pytest.fixture(params=sorted(PAIRS))
def layout_lite(request: pytest.FixtureRequest) -> LayoutLiteDc:
    """The LayoutLite the scada emits for each fixture layout, as the LTN reads it."""
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return LayoutLiteDc(app.scada.layout_lite)


def test_store_tanks_come_from_the_layout(layout_lite: LayoutLiteDc) -> None:
    assert layout_lite.has_store_tanks
    assert sorted(layout_lite.store_tanks) == list(range(1, layout_lite.total_store_tanks + 1))
    for tank in layout_lite.store_tanks.values():
        assert tank.reader in layout_lite.sh_node_by_name


def test_store_tank_temp_channels_are_in_the_registry(layout_lite: LayoutLiteDc) -> None:
    store = layout_lite.store_tank_temp_channel_names
    assert store == sorted(
        d for tank in layout_lite.store_tanks.values() for d in tank.effective
    )
    for name in layout_lite.tank_temp_channel_names:
        assert layout_lite.channel_registry.get(name) is not None


def test_no_tank_nodes_means_no_store_tanks(layout_lite: LayoutLiteDc) -> None:
    readers = {tank.reader for tank in layout_lite.store_tanks.values()}
    gt = layout_lite.gt.model_copy(
        update={"ShNodes": [n for n in layout_lite.gt.ShNodes if n.Name not in readers]}
    )
    slab = LayoutLiteDc(gt)
    assert not slab.has_store_tanks
    assert slab.store_tank_temp_channel_names == []

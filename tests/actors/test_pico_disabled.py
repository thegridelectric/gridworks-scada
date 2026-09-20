"""A pico component with Enabled false is installed but out of service: the
scada serves it no web routes, its actor never reports it missing or its
channels flatlined, and the pico-cycler neither lists it nor cycles for it.
Its nodes and channels stay in the layout and carry no readings."""

import asyncio
import json
from pathlib import Path

import pytest

from actors.api_tank_module import ApiTankModule
from actors.pico_cycler import PicoCycler
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
LAYOUT = "gw.nolan.layout.json"
OPS = "gw.nolan.operational.params.json"
DISABLED = "floor1"


def boot(tmp_path: Path) -> ScadaApp:
    layout = json.loads((CONFIG / LAYOUT).read_text())
    node = next(n for n in layout["ShNodes"] if n["Name"] == DISABLED)
    component = next(c for c in layout["Components"] if c["ComponentId"] == node["ComponentId"])
    component["Enabled"] = False
    layout_path = tmp_path / LAYOUT
    layout_path.write_text(json.dumps(layout))
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = layout_path
    settings.paths.operational_params = CONFIG / OPS
    settings.paths.mkdirs()
    app = ScadaApp(app_settings=settings)
    app.instantiate()
    return app


def test_the_cycler_does_not_list_a_disabled_pico(tmp_path: Path) -> None:
    app = boot(tmp_path)
    cycler = app.scada.get_communicator(HSNN.pico_cycler)
    assert isinstance(cycler, PicoCycler)
    assert DISABLED not in {actor.name for actor in cycler.pico_actors}
    assert "fancoil" in {actor.name for actor in cycler.pico_actors}
    assert len(cycler.picos) == len(cycler.pico_actors) == len(cycler.pico_by_actor)


def test_the_layout_keeps_a_disabled_picos_channels(tmp_path: Path) -> None:
    layout = boot(tmp_path).scada.layout
    for depth in (1, 2, 3):
        assert f"{DISABLED}-depth{depth}-device" in layout.data_channels
    assert "zone1-bedrooms-floor-temp" in layout.derived_channels


@pytest.mark.asyncio
async def test_a_disabled_pico_actor_never_reports_missing(tmp_path: Path) -> None:
    app = boot(tmp_path)
    tank = app.get_communicator_as_type(DISABLED, ApiTankModule)
    assert tank is not None
    sent: list = []
    tank._send_to = lambda dst, payload, src=None: sent.append(payload)
    tank._send = lambda message: None
    tank.liveness.report_due = lambda now: True

    task = asyncio.create_task(tank.main())
    await asyncio.sleep(0.05)
    tank._stop_requested = True
    task.cancel()

    assert sent == []


@pytest.mark.asyncio
async def test_an_enabled_pico_actor_reports_missing_when_due(tmp_path: Path) -> None:
    app = boot(tmp_path)
    tank = app.get_communicator_as_type("fancoil", ApiTankModule)
    assert tank is not None
    sent: list = []
    tank._send_to = lambda dst, payload, src=None: sent.append(payload)
    tank._send = lambda message: None
    tank.liveness.report_due = lambda now: True

    task = asyncio.create_task(tank.main())
    await asyncio.sleep(0.05)
    tank._stop_requested = True
    task.cancel()

    assert sent

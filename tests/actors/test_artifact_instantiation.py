"""Instantiates a ScadaApp on the ASSEMBLED sim-spruce pair — the
whole-artifact regression test the first spruce window lacked: every actor
constructs through the ordinary boot path (LocalControl resolves to
NolanLocalControl, the i2c relays and bus register), and the snapshot path
builds. The window #1 killer was scada_data.capture_seconds
walking the DAC writer's i2c.dac.channel.config — a config shape the pinned
Nolan fixture never exercises, which is why 189 green tests missed it.

The frozen fixtures are the VERBATIM tlayouts artifacts (static layout +
ops params) so the boot exercises its real assembly path; refresh both from
tlayouts output/spruce-sim/ when the layout changes."""

from pathlib import Path

import pytest

from actors.local_control.nolan import NolanLocalControl
from scada_app import ScadaApp

SPRUCE_LAYOUT = Path(__file__).parent.parent / "config" / "gw.nolan.layout.json"
SPRUCE_OPS = (
    Path(__file__).parent.parent
    / "config"
    / "gw.nolan.operational.params.json"
)


@pytest.fixture
def app() -> ScadaApp:
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = SPRUCE_LAYOUT
    # conftest pins the Nolan fixture's ops file via env; point at spruce's
    settings.paths.operational_params = SPRUCE_OPS
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def test_spruce_artifact_boots(app: ScadaApp) -> None:
    names = app.raw_proactor.get_communicator_names()
    assert "i2c-bus" in names
    assert "zone1-bedrooms-failsafe-relay" in names
    assert "secondary-pump-relay" in names
    lc = app.raw_proactor.get_communicator("lc")
    assert isinstance(lc._impl, NolanLocalControl)


def test_spruce_snapshot_path_builds(app: ScadaApp) -> None:
    data = app.scada._data
    # the window #1 killer path, hit directly for every channel
    for ch in app.hardware_layout.data_channels.values():
        assert isinstance(data.capture_seconds(ch), int)
    snap = data.make_snapshot()
    assert snap.TypeName == "snapshot.spaceheat"

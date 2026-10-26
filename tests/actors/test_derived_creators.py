"""Every derived channel the layout names a scada actor creator of is made
by that actor, and every actor's claim is a channel the layout names it
creator of. A named creator that never sends on its channel leaves the
channel out of the snapshot and the report with no fault in the log; boot
refuses the layout instead."""

import json
from pathlib import Path

import pytest
from gwproactor_test.certs import copy_keys, uses_tls

from scada_app import DerivedChannelCreator, ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")
ORANGE = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")


def boot(layout: Path, ops: Path) -> ScadaApp:
    settings = ScadaApp.get_settings()
    if uses_tls(settings):
        copy_keys("scada", settings)
    settings.paths.hardware_layout = layout
    settings.paths.operational_params = ops
    settings.paths.mkdirs()
    return ScadaApp(app_settings=settings).instantiate()


def claims(app: ScadaApp) -> dict[str, set[str]]:
    proactor = app.raw_proactor
    return {
        name: proactor.get_communicator(name).derived_channels_created()
        for name in proactor.get_communicator_names()
        if isinstance(proactor.get_communicator(name), DerivedChannelCreator)
    }


@pytest.mark.parametrize("layout, ops", [NOLAN, ORANGE, WILLOW])
def test_every_declared_creator_claims_its_channel(layout: str, ops: str) -> None:
    app = boot(CONFIG / layout, CONFIG / ops)
    layout_dc = app.hardware_layout
    declared: dict[str, set[str]] = {}
    for dc in layout_dc.derived_channels.values():
        if not layout_dc.channel_disabled(dc.Name):
            declared.setdefault(dc.CreatedByNodeName, set()).add(dc.Name)
    assert claims(app) == declared
    assert claims(app)["power-meter"] == {"transactive-power"}


def test_a_creator_that_does_not_claim_its_channel_is_refused(tmp_path: Path) -> None:
    layout = json.loads((CONFIG / NOLAN[0]).read_text())
    identity = next(dc for dc in layout["DerivedChannels"] if dc["Strategy"] == "identity")
    identity["CreatedByNodeName"] = "power-meter"
    path = tmp_path / NOLAN[0]
    path.write_text(json.dumps(layout))
    with pytest.raises(ValueError, match=f"{identity['Name']} is created by power-meter, which does not claim it"):
        boot(path, CONFIG / NOLAN[1])

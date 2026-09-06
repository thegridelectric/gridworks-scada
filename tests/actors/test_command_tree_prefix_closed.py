"""The scada's command-tree builders emit trees that satisfy new.command.tree
axiom 1 (PrefixClosedHandles), for every boss the scada hands control to, on
both authored pairs.

`NewCommandTree` now enforces the axiom at construction, so an orphan-prefix
handle assignment fails here instead of going on the wire and being dropped by
the consumer's decode."""

from pathlib import Path

import pytest

from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import MainAutoEvent
from gwsproto.named_types import GoDormant, NewCommandTree
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


@pytest.fixture(params=sorted(PAIRS))
def app(request: pytest.FixtureRequest) -> ScadaApp:
    layout, ops = PAIRS[request.param]
    settings = ScadaApp.get_settings()
    settings.paths.hardware_layout = CONFIG / layout
    settings.paths.operational_params = CONFIG / ops
    settings.paths.mkdirs()
    scada_app = ScadaApp(app_settings=settings)
    scada_app.instantiate()
    return scada_app


def capture(scada) -> list:
    sent: list = []
    scada._send_to = lambda dst, payload, src=None: sent.append((dst.name, payload))
    return sent


@pytest.mark.parametrize("boss", ["admin", "local_control", "leaf_ally"])
def test_scada_command_tree_is_prefix_closed(app: ScadaApp, boss: str) -> None:
    scada = app.scada
    sent = capture(scada)
    scada.set_command_tree(getattr(scada, boss))
    trees = [p for _, p in sent if isinstance(p, NewCommandTree)]
    assert len(trees) == 1
    # Construction already ran axiom 1; re-validate the wire form explicitly.
    NewCommandTree.model_validate(trees[0].model_dump(by_alias=True, exclude_none=True))


def test_admin_tree_leaves_vdc_relay_under_pico_cycler(app: ScadaApp) -> None:
    """HACK (2026-09-06): admin's tree does not take vdc-relay; it stays under
    auto.pico-cycler so the cycler keeps rebooting flatlined picos during an
    admin window. Goes with Scada.HACK_VDC_RELAY_NAME."""
    scada = app.scada
    capture(scada)
    scada.set_command_tree(scada.admin)
    vdc = scada.layout.vdc_relay
    assert vdc.name == scada.HACK_VDC_RELAY_NAME
    assert vdc.handle == f"{H0N.auto}.{H0N.pico_cycler}.{vdc.name}"
    others = [n for n in scada.layout.actuators if n.Name != vdc.name]
    assert others
    assert all(n.handle.startswith(f"{H0N.admin}.") for n in others)


def test_auto_goes_dormant_leaves_pico_cycler_awake(app: ScadaApp) -> None:
    """HACK (2026-09-06): admin waking the scada sends GoDormant to leaf-ally
    and local-control only; the pico-cycler runs in every top state."""
    scada = app.scada
    sent = capture(scada)
    scada.auto_trigger(MainAutoEvent.AutoGoesDormant)
    dormant_to = sorted(dst for dst, p in sent if isinstance(p, GoDormant))
    assert dormant_to == sorted([scada.leaf_ally.name, scada.local_control.name])
    assert H0N.pico_cycler not in dormant_to

"""The scada's command-tree builders emit trees that satisfy new.command.tree
axiom 1 (PrefixClosedHandles), for every boss the scada hands control to, on
both authored pairs.

`NewCommandTree` now enforces the axiom at construction, so an orphan-prefix
handle assignment fails here instead of going on the wire and being dropped by
the consumer's decode."""

from pathlib import Path

import pytest

from gwsproto.named_types import NewCommandTree
from scada_app import ScadaApp

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
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

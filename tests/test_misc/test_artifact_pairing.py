"""The loader boots only a layout ⊕ ops pair of one family and one Scada."""

import json
from pathlib import Path

import pytest

from sema_to_dc import ops_and_sema_to_dc

CONFIG = Path(__file__).parent.parent / "config"
NOLAN = ("gw.nolan.layout.json", "gw.nolan.operational.params.json")
ORANGE = ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json")
WILLOW = ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json")


@pytest.mark.parametrize("layout, ops", [NOLAN, ORANGE, WILLOW])
def test_fixture_pairs_load(layout: str, ops: str) -> None:
    ops_and_sema_to_dc(CONFIG / layout, CONFIG / ops)


def test_crossed_families_refused() -> None:
    with pytest.raises(ValueError, match="Mismatched artifact pair.*family params"):
        ops_and_sema_to_dc(CONFIG / NOLAN[0], CONFIG / ORANGE[1])


def test_another_scadas_ops_refused(tmp_path: Path) -> None:
    """Same family, right shape, another Scada's alias."""
    ops = json.loads((CONFIG / ORANGE[1]).read_text())
    ops["ScadaAlias"] = json.loads((CONFIG / WILLOW[1]).read_text())["ScadaAlias"]
    path = tmp_path / "ops.json"
    path.write_text(json.dumps(ops))
    with pytest.raises(ValueError, match="ScadaAlias"):
        ops_and_sema_to_dc(CONFIG / ORANGE[0], path)


def test_retired_ops_word_refused(tmp_path: Path) -> None:
    ops = json.loads((CONFIG / NOLAN[1]).read_text())
    ops["TypeName"] = "gw.nolan.operational.params"
    path = tmp_path / "ops.json"
    path.write_text(json.dumps(ops))
    with pytest.raises(ValueError, match="gw.operational.params"):
        ops_and_sema_to_dc(CONFIG / NOLAN[0], path)

"""A broken layout is refused by the layout word's axioms on the load path,
before any data class is built. Each test breaks one thing in a copy of a
fixture layout and loads it through ops_and_sema_to_dc."""

import json
from pathlib import Path
from typing import Callable

import pytest

from sema_to_dc import ops_and_sema_to_dc

CONFIG = Path(__file__).parent.parent / "config"
# (layout, ops, number of DerivedChannelInputsAcyclic in that layout word);
# DataChannelNodeResolution is the axiom before it and
# DerivedChannelCreatorResolution the one before that.
PAIRS = {
    "nolan": ("gw.nolan.layout.json", "gw.nolan.operational.params.json", 18),
    "house0-willow": (
        "gw.house0.willow.layout.json",
        "gw.house0.willow.operational.params.json",
        22,
    ),
}


def load_broken(tmp_path: Path, layout: str, ops: str, mutate: Callable[[dict], None]) -> None:
    d = json.loads((CONFIG / layout).read_text())
    mutate(d)
    path = tmp_path / layout
    path.write_text(json.dumps(d))
    ops_and_sema_to_dc(path, CONFIG / ops)


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_a_derived_input_naming_no_channel_is_refused_by_the_word(
    tmp_path: Path, pair: str
) -> None:
    layout, ops, axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        identity = next(c for c in d["DerivedChannels"] if c["Strategy"] == "identity")
        identity["InputChannelNames"] = ["no-such-channel"]

    with pytest.raises(ValueError, match=rf"Axiom {axiom} \(.*failed \(a\)"):
        load_broken(tmp_path, layout, ops, mutate)


@pytest.mark.parametrize("pair", sorted(PAIRS))
@pytest.mark.parametrize(
    ("field", "clause"), [("AboutNodeName", "a"), ("CapturedByNodeName", "b")]
)
def test_a_data_channel_naming_no_node_is_refused_by_the_word(
    tmp_path: Path, pair: str, field: str, clause: str
) -> None:
    layout, ops, inputs_axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        d["DataChannels"][-1][field] = "no-such-node"

    with pytest.raises(ValueError, match=rf"Axiom {inputs_axiom - 1} \(.*failed \({clause}\)"):
        load_broken(tmp_path, layout, ops, mutate)


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_a_derived_channel_naming_no_creating_node_is_refused_by_the_word(
    tmp_path: Path, pair: str
) -> None:
    layout, ops, inputs_axiom = PAIRS[pair]

    def mutate(d: dict) -> None:
        identity = next(c for c in d["DerivedChannels"] if c["Strategy"] == "identity")
        identity["CreatedByNodeName"] = "no-such-node"

    with pytest.raises(ValueError, match=rf"Axiom {inputs_axiom - 2} \(.*failed \(a\)"):
        load_broken(tmp_path, layout, ops, mutate)

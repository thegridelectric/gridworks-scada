"""Rejecting tests for gw.nolan.layout/000's seven axioms.

Each counterexample is a typed mutation of the assembled fixture pair,
re-validated at the boundary — chosen so the intended axiom fires (not an
earlier one; e.g. dropping a transactive-metered node would trip axiom 1
before axiom 5 saw it)."""

import json
from pathlib import Path

import pytest

from gwsproto.named_types import NolanLayout, NolanOperationalParams
from sema_to_dc import assemble_runtime_layout

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture(scope="module")
def assembled() -> dict:
    ops = NolanOperationalParams.model_validate_json(
        (CONFIG / "gw.nolan.operational.params.json").read_text()
    )
    return assemble_runtime_layout(
        json.loads((CONFIG / "gw.nolan.layout.json").read_text()),
        ops.model_dump(by_alias=True, exclude_none=True),
    )


def mutated(assembled: dict, mutate) -> dict:
    d = json.loads(json.dumps(assembled))
    mutate(d)
    return d


def reject(assembled: dict, mutate, axiom: str) -> None:
    with pytest.raises(ValueError, match=axiom):
        NolanLayout.model_validate(mutated(assembled, mutate))


def test_gw_nolan_layout_generated(assembled: dict) -> None:
    NolanLayout.model_validate(assembled)


def test_gw_nolan_layout_axiom_1(assembled: dict) -> None:
    """Exactly one transactive-power DerivedChannel."""
    reject(
        assembled,
        lambda d: d.update(
            DerivedChannels=[
                c for c in d["DerivedChannels"] if c["Strategy"] != "transactive-power"
            ]
        ),
        "Axiom 1",
    )


def test_gw_nolan_layout_axiom_2(assembled: dict) -> None:
    """A board-resident component's BoardComponentId must resolve."""

    def dangle(d: dict) -> None:
        for c in d["Components"]:
            if c["TypeName"] == "gpio.relay.component.gt":
                c["BoardComponentId"] = "00000000-0000-4000-8000-000000000000"

    reject(assembled, dangle, "Axiom 2")


def test_gw_nolan_layout_axiom_3(assembled: dict) -> None:
    """The charge valve is a required plant relay."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "charge-valve-relay"]
        ),
        "Axiom 3",
    )


def test_gw_nolan_layout_axiom_4(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "derived-generator"]
        ),
        "Axiom 4",
    )


def test_gw_nolan_layout_axiom_5(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(ShNodes=[n for n in d["ShNodes"] if n["Name"] != "ltn"]),
        "Axiom 5",
    )


def test_gw_nolan_layout_axiom_5_hp_boss(assembled: dict) -> None:
    """hp-boss is a required command node in every layout."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "hp-boss"]
        ),
        "Axiom 5",
    )


def test_gw_nolan_layout_axiom_6(assembled: dict) -> None:
    """dist-flow is required and not transactive, so axiom 6 itself fires."""
    reject(
        assembled,
        lambda d: d.update(
            DataChannels=[c for c in d["DataChannels"] if c["Name"] != "dist-flow"]
        ),
        "Axiom 6",
    )


def test_gw_nolan_layout_axiom_6_elt_pwr(assembled: dict) -> None:
    """The four resistive-element power channels are required sensing.

    The channel is also a transactive-boundary input, so the mutation
    removes it from InputChannelNames too — otherwise the transactive
    axiom fires first."""
    def mutate(d: dict) -> None:
        d["DataChannels"] = [
            c for c in d["DataChannels"] if c["Name"] != "elt-store-top-pwr"
        ]
        for c in d["DerivedChannels"]:
            if c.get("Strategy") == "transactive-power":
                c["InputChannelNames"] = [
                    n for n in c["InputChannelNames"] if n != "elt-store-top-pwr"
                ]
    reject(assembled, mutate, "Axiom 6")


def test_gw_nolan_layout_axiom_7(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d["Hydronic"].update(TotalStoreTanks=2),
        "Axiom 7",
    )


def test_gw_hydronic_axiom_3(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    h["ZoneCallCircuits"][0]["ServesZone"] = "no-such-zone"
    with pytest.raises(ValueError, match="Axiom 3"):
        Hydronic.model_validate(h)


def test_gw_hydronic_axiom_4(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    circ = h["ZoneCallCircuits"][0]
    circ["SetpointSource"] = "Learned"
    for z in h["Zones"]:
        if z["Name"] == circ["ServesZone"]:
            z.pop("TempChannelName", None)
    with pytest.raises(ValueError, match="Axiom 4"):
        Hydronic.model_validate(h)


def test_gw_nolan_layout_component_binding(assembled: dict) -> None:
    """Every component is HAD by exactly one ShNode; the node's Name is the
    component's human-meaning identity within the house (ComponentId is the
    replaceable instance under it). Becomes a layout axiom in the
    RequiredEquipment round."""
    from collections import Counter

    refs = Counter(
        n["ComponentId"] for n in assembled["ShNodes"] if n.get("ComponentId")
    )
    violations = {
        c["ComponentId"]: refs.get(c["ComponentId"], 0)
        for c in assembled["Components"]
        if refs.get(c["ComponentId"], 0) != 1
    }
    assert not violations, violations

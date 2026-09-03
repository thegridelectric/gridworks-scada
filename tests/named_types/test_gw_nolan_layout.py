"""Rejecting tests for gw.nolan.layout/000's nine axioms.

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
    """A core node missing."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "derived-generator"]
        ),
        "Axiom 3",
    )


def test_gw_nolan_layout_axiom_3_exact_match(assembled: dict) -> None:
    """A second node with a core name is rejected."""
    def duplicate(d: dict) -> None:
        ltn = next(n for n in d["ShNodes"] if n["Name"] == "ltn")
        d["ShNodes"].append(dict(ltn, ShNodeId="00000000-0000-4000-8000-000000000000"))
    reject(assembled, duplicate, "Axiom 3")


def test_gw_nolan_layout_axiom_4_hp_boss(assembled: dict) -> None:
    """hp-boss is a required command node in every layout."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "hp-boss"]
        ),
        "Axiom 4",
    )


def test_gw_nolan_layout_axiom_4_n_handle(assembled: dict) -> None:
    def rehandle(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "n":
                n["Handle"] = "auto.n"
    reject(assembled, rehandle, "Axiom 4")


def test_gw_nolan_layout_axiom_5(assembled: dict) -> None:
    """The charge valve is a required plant relay."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "charge-valve-relay"]
        ),
        "Axiom 5",
    )


def test_gw_nolan_layout_axiom_5_tank1_elt(assembled: dict) -> None:
    """The store tank's element relays carry the per-tank name."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "tank1-top-elt-relay"]
        ),
        "Axiom 5",
    )


def test_gw_nolan_layout_axiom_5_circuits(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d["Hydronic"].update(ZoneCallCircuits=[]),
        "Axiom 5",
    )


def test_gw_nolan_layout_axiom_6_component(assembled: dict) -> None:
    """hp-ctrl-box is equipment: it carries a component."""
    def unbind(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-ctrl-box":
                n.pop("ComponentId")
    reject(assembled, unbind, "Axiom 6")


def test_gw_nolan_layout_axiom_6_actor_class(assembled: dict) -> None:
    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["ActorClass"] = "Relay"
                n["ActorHierarchyName"] = "s.hp-odu"
    reject(assembled, reclass, "Axiom 6")


def test_gw_nolan_layout_axiom_7(assembled: dict) -> None:
    """Every component is HAD by exactly one ShNode: an orphan component
    (its node dropped its ComponentId) is rejected. The web server has no
    other axiom guarding it, so axiom 7 itself fires."""
    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "web-server":
                n.pop("ComponentId")
    reject(assembled, orphan, "Axiom 7")


def test_gw_nolan_layout_axiom_8(assembled: dict) -> None:
    """dist-flow is required and not transactive, so axiom 8 itself fires."""
    reject(
        assembled,
        lambda d: d.update(
            DataChannels=[c for c in d["DataChannels"] if c["Name"] != "dist-flow"]
        ),
        "Axiom 8",
    )


def test_gw_nolan_layout_axiom_8_elt_pwr(assembled: dict) -> None:
    """The four resistive-element power channels are required sensing.

    The channel is also a transactive-boundary input, so the mutation
    removes it from InputChannelNames too — otherwise the transactive
    axiom fires first."""
    def mutate(d: dict) -> None:
        d["DataChannels"] = [
            c for c in d["DataChannels"] if c["Name"] != "tank1-top-elt-pwr"
        ]
        for c in d["DerivedChannels"]:
            if c.get("Strategy") == "transactive-power":
                c["InputChannelNames"] = [
                    n for n in c["InputChannelNames"] if n != "tank1-top-elt-pwr"
                ]
    reject(assembled, mutate, "Axiom 8")


def test_gw_nolan_layout_axiom_9(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d["Hydronic"].update(TotalStoreTanks=2),
        "Axiom 9",
    )


def test_gw_hydronic_axiom_2(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    h["ZoneCallCircuits"][0]["ServesZone"] = "no-such-zone"
    with pytest.raises(ValueError, match="Axiom 2"):
        Hydronic.model_validate(h)


def test_gw_hydronic_axiom_3(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    circ = h["ZoneCallCircuits"][0]
    circ["SetpointSource"] = "Learned"
    for z in h["Zones"]:
        if z["Name"] == circ["ServesZone"]:
            z.pop("TempChannelName", None)
    with pytest.raises(ValueError, match="Axiom 3"):
        Hydronic.model_validate(h)

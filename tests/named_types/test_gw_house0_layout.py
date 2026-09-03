"""Rejecting tests for gw.house0.layout/000's ported axioms (2, 3, 7, 8, 10, 11).

Each counterexample is a typed mutation of the assembled fixture pair,
re-validated at the boundary — chosen so the intended axiom fires. Axioms
1, 4, 5 predate this file; 6 and 9 are unported (see the axiom-coverage
allowlists)."""

import json
from pathlib import Path

import pytest

from gwsproto.named_types import House0Layout, House0OperationalParams, NolanLayout
from sema_to_dc import assemble_runtime_layout, check_sieg_loop_assembly

CONFIG = Path(__file__).parent.parent / "config"


PAIRS = {
    "house0": ("gw.house0.layout.json", "gw.house0.operational.params.json"),
    "house0-sim": (
        "gw.house0.sim.layout.json",
        "gw.house0.sim.operational.params.json",
    ),
}


@pytest.fixture(scope="module", params=sorted(PAIRS))
def assembled(request: pytest.FixtureRequest) -> dict:
    layout, ops_file = PAIRS[request.param]
    ops = House0OperationalParams.model_validate_json((CONFIG / ops_file).read_text())
    return assemble_runtime_layout(
        json.loads((CONFIG / layout).read_text()),
        ops.model_dump(by_alias=True, exclude_none=True),
    )


def mutated(assembled: dict, mutate) -> dict:
    d = json.loads(json.dumps(assembled))
    mutate(d)
    return d


def reject(assembled: dict, mutate, axiom: str) -> None:
    with pytest.raises(ValueError, match=axiom):
        House0Layout.model_validate(mutated(assembled, mutate))


def test_gw_house0_layout_generated(assembled: dict) -> None:
    House0Layout.model_validate(assembled)


def test_gw_house0_layout_axiom_2(assembled: dict) -> None:
    """derived-generator with the wrong ActorClass fails the core pair check."""
    def mutate(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "derived-generator":
                n["ActorClass"] = "NoActor"
                n.pop("ActorHierarchyName", None)
    reject(assembled, mutate, "Axiom 2")


def test_gw_house0_layout_axiom_3(assembled: dict) -> None:
    """sieg-loop is an unconditional command node — removing it fails."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "sieg-loop"]
        ),
        "Axiom 3",
    )


def test_gw_house0_layout_axiom_3_n_handle(assembled: dict) -> None:
    """'n' must have effective handle auto.lc.n."""
    def mutate(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "n":
                n["Handle"] = "auto.n"
    reject(assembled, mutate, "Axiom 3")


def test_gw_house0_layout_axiom_7(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(
            DataChannels=[c for c in d["DataChannels"] if c["Name"] != "store-flow"]
        ),
        "Axiom 7",
    )


def test_gw_house0_layout_axiom_8(assembled: dict) -> None:
    """The sieg manifold surface is unconditional for gw.house0.layout."""
    reject(
        assembled,
        lambda d: d.update(
            DataChannels=[c for c in d["DataChannels"] if c["Name"] != "sieg-cold"]
        ),
        "Axiom 8",
    )


def test_gw_house0_layout_axiom_6(assembled: dict) -> None:
    """A transactive input whose about-node loses NameplatePowerW fails."""
    def mutate(d: dict) -> None:
        tx = [c for c in d["DerivedChannels"] if c.get("Strategy") == "transactive-power"][0]
        about = {c["Name"]: c["AboutNodeName"] for c in d["DataChannels"]}[tx["InputChannelNames"][0]]
        for n in d["ShNodes"]:
            if n["Name"] == about:
                n.pop("NameplatePowerW", None)
    reject(assembled, mutate, "Axiom 6")


def test_gw_house0_layout_axiom_9(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(
            DerivedChannels=[c for c in d["DerivedChannels"] if c["Name"] != "usable-energy"]
        ),
        "Axiom 9",
    )


@pytest.mark.skip(
    reason="krida multichannel relay component is many-to-one (14 relay "
    "nodes) until the krida retirement; ComponentBinding lands there"
)
def test_gw_house0_layout_component_binding(assembled: dict) -> None:
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


def test_gw_house0_layout_axiom_10_relay(assembled: dict) -> None:
    """The aquastat control relay is a required plant relay."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "aquastat-ctrl-relay"]
        ),
        "Axiom 10",
    )


def test_gw_house0_layout_axiom_10_output(assembled: dict) -> None:
    """A 0-10V output with the wrong ActorClass fails clause a."""

    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "store-010v":
                n["ActorClass"] = "NoActor"
                n.pop("ActorHierarchyName", None)

    reject(assembled, reclass, "Axiom 10")


def test_gw_house0_layout_axiom_10_circuits(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d["Hydronic"].update(ZoneCallCircuits=[]),
        "Axiom 10",
    )


def test_gw_house0_layout_axiom_11_component(assembled: dict) -> None:
    """hp-idu is equipment: it carries a component."""

    def unbind(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-idu":
                n.pop("ComponentId")

    reject(assembled, unbind, "Axiom 11")


def test_gw_house0_layout_axiom_11_actor_class(assembled: dict) -> None:
    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["ActorClass"] = "Relay"
                n["ActorHierarchyName"] = "s.hp-odu"

    reject(assembled, reclass, "Axiom 11")


def test_sieg_loop_assembly_check(assembled: dict) -> None:
    """Ops asking for the loop needs a SiegLoop-classed node in the layout:
    the House0 pair passes; the same ops over the Nolan layout (no loop)
    refuses at assembly, the check that replaced gw.hydronic's old axiom 1."""
    layout = House0Layout.model_validate(assembled)
    ops = House0OperationalParams.model_validate_json(
        (CONFIG / "gw.house0.operational.params.json").read_text()
    ).model_copy(update={"UseSiegLoop": True})
    check_sieg_loop_assembly(layout, ops)
    nolan = NolanLayout.model_validate_json(
        (CONFIG / "gw.nolan.layout.json").read_text()
    )
    with pytest.raises(ValueError, match="SiegLoop"):
        check_sieg_loop_assembly(nolan, ops)


def declare_twin(d: dict, name: str = "hp-idu", handle: str | None = "auto.lc.n.hp-boss.hp-idu") -> None:
    d["Hydronic"]["HpCommandNodeName"] = name
    for n in d["ShNodes"]:
        if n["Name"] == name:
            n["ActorClass"] = "HpTwin"
            n["ActorHierarchyName"] = f"s.{name}"
            if handle is not None:
                n["Handle"] = handle


def test_gw_house0_layout_axiom_12_declared_twin_accepted(assembled: dict) -> None:
    """A declared hp-idu twin under hp-boss satisfies both clauses."""
    House0Layout.model_validate(mutated(assembled, declare_twin))


def test_gw_house0_layout_axiom_12_a_no_actor(assembled: dict) -> None:
    """Declared but left NoActor."""
    def declare_only(d: dict) -> None:
        d["Hydronic"]["HpCommandNodeName"] = "hp-idu"
    reject(assembled, declare_only, "Axiom 12")


def test_gw_house0_layout_axiom_12_a_wrong_parent(assembled: dict) -> None:
    """The twin must hang directly under hp-boss."""
    reject(assembled, lambda d: declare_twin(d, handle="auto.lc.n.hp-idu"), "Axiom 12")


def test_gw_house0_layout_axiom_12_a_unknown_name(assembled: dict) -> None:
    """hp-ctrl-box is a legal target name but a House0 layout has no such node."""
    def declare_missing(d: dict) -> None:
        d["Hydronic"]["HpCommandNodeName"] = "hp-ctrl-box"
    reject(assembled, declare_missing, "Axiom 12")


def test_gw_house0_layout_axiom_12_b_undeclared_twin(assembled: dict) -> None:
    """An HpTwin node with no declaration. Exercised on a node no other
    axiom pins, so clause b is the only guard."""
    def stray_twin(d: dict) -> None:
        d["ShNodes"].append(
            {
                "Name": "stray-twin",
                "ActorClass": "HpTwin",
                "ActorHierarchyName": "s.stray-twin",
                "ShNodeId": "0f2b7c1e-5d3a-4b8e-9c6f-1a2b3c4d5e6f",
                "TypeName": "spaceheat.node.gt",
                "Version": "302",
            }
        )
    reject(assembled, stray_twin, "Axiom 12")


def test_gw_house0_layout_axiom_13(assembled: dict) -> None:
    """A relay handle whose parent names no ShNode is an orphan."""
    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n["Handle"] = "auto.nobody.vdc-relay"
    reject(assembled, orphan, "Axiom 13")


def test_gw_house0_layout_axiom_14_a(assembled: dict) -> None:
    """An actuator with a bare Name for a handle has no boss."""
    def undotted(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n.pop("Handle", None)
    reject(assembled, undotted, "Axiom 14")


def test_gw_house0_layout_axiom_14_b(assembled: dict) -> None:
    """hp-odu (NoActor) given a handle under hp-boss is a leaf that is
    neither actuator nor command node."""
    def stray_leaf(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["Handle"] = "auto.lc.n.hp-boss.hp-odu"
    reject(assembled, stray_leaf, "Axiom 14")

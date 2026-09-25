"""Rejecting tests for gw.house0.layout/000's ported axioms (2, 3, 7, 8, 10, 11).

Each counterexample is a typed mutation of the assembled fixture pair,
re-validated at the boundary — chosen so the intended axiom fires. Axioms
1, 4, 5 predate this file; 6 and 9 are unported (see the axiom-coverage
allowlists)."""

import json
import uuid
from pathlib import Path

import pytest

from gwsproto.enums import SiegLoopStrategy
from gwsproto.named_types import House0Layout, OperationalParams
from sema_to_dc import assemble_runtime_layout, check_sieg_loop_strategy

CONFIG = Path(__file__).parent.parent / "config"


PAIRS = {
    "house0-willow": ("gw.house0.willow.layout.json", "gw.house0.willow.operational.params.json"),
    "house0-orange": ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
}


@pytest.fixture(scope="module", params=sorted(PAIRS))
def assembled(request: pytest.FixtureRequest) -> dict:
    layout, ops_file = PAIRS[request.param]
    ops = OperationalParams.model_validate_json((CONFIG / ops_file).read_text())
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

def sensor_off_the_meter(d: dict) -> str:
    """A node capturing channels that feed no transactive-power channel and
    is not an actuator: the one a disabled-list test may disable without
    tripping the transactive or actuator clauses."""
    metered = {
        n
        for x in d["DerivedChannels"]
        if x["Strategy"] == "transactive-power"
        for n in x["InputChannelNames"]
    }
    actuators = {
        n["Name"] for n in d["ShNodes"] if n["ActorClass"] in ("Relay", "ZeroTenOutputer")
    }
    captured: dict[str, set[str]] = {}
    for c in d["DataChannels"]:
        captured.setdefault(c["CapturedByNodeName"], set()).add(c["Name"])
    return next(
        node
        for node, names in captured.items()
        if not names & metered and node not in actuators
    )


def unmetered_derived(d: dict) -> dict:
    """A DerivedChannel with inputs, none of them in the transactive set."""
    metered = {
        n
        for x in d["DerivedChannels"]
        if x["Strategy"] == "transactive-power"
        for n in x["InputChannelNames"]
    }
    return next(
        c for c in d["DerivedChannels"]
        if c["InputChannelNames"] and not set(c["InputChannelNames"]) & metered
    )



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


def set_handle(name: str, handle: str):
    def mutate(d: dict) -> None:
        next(n for n in d["ShNodes"] if n["Name"] == name)["Handle"] = handle
    return mutate


def test_gw_house0_layout_axiom_33_command_node_declared_under_lc(assembled: dict) -> None:
    """hp-boss and its relay move together so the tree stays prefix-closed
    and the handle axiom is the one that rejects."""
    def mutate(d: dict) -> None:
        set_handle("hp-boss", "auto.lc.n.hp-boss")(d)
        set_handle("hp-scada-ops-relay", "auto.lc.n.hp-boss.hp-scada-ops-relay")(d)
    reject(assembled, mutate, "Axiom 33")


def test_gw_house0_layout_axiom_33_fixed_relay_declared_flat(assembled: dict) -> None:
    reject(assembled, set_handle("hp-loop-on-off-relay", "auto.hp-loop-on-off-relay"), "Axiom 33")


def test_gw_house0_layout_axiom_33_floating_actuator_under_a_boss(assembled: dict) -> None:
    reject(assembled, set_handle("store-pump-relay", "auto.lc.n.store-pump-relay"), "Axiom 33")


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


def test_gw_house0_layout_axiom_15(assembled: dict) -> None:
    """Every component is HAD by exactly one ShNode: an orphan component
    (its node dropped its ComponentId) is rejected. The web server has no
    other axiom guarding it, so axiom 15 itself fires."""

    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "web-server":
                n.pop("ComponentId")

    reject(assembled, orphan, "Axiom 15")


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


def test_gw_house0_layout_axiom_10_output_component(assembled: dict) -> None:
    """A 0-10V output bound to something other than a DAC output component
    fails clause c; the web server's component stands in for the wrong kind
    (and the web-server node loses its own binding so axiom 15 stays quiet)."""

    def rebind(d: dict) -> None:
        web = next(c for c in d["Components"] if c["TypeName"] == "web.server.component.gt")
        for n in d["ShNodes"]:
            if n["Name"] == "web-server":
                n.pop("ComponentId")
            if n["Name"] == "dist-010v":
                n["ComponentId"] = web["ComponentId"]

    reject(assembled, rebind, "Axiom 10")


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


def test_sieg_loop_strategy_check() -> None:
    """The loader takes HoldFullSend and StratProtect and refuses LwtControl,
    which is not built."""
    ops = OperationalParams.model_validate_json(
        (CONFIG / "gw.house0.orange.operational.params.json").read_text()
    )
    for strategy in (SiegLoopStrategy.HoldFullSend, SiegLoopStrategy.StratProtect):
        check_sieg_loop_strategy(
            ops.model_copy(
                update={
                    "FamilyParams": ops.FamilyParams.model_copy(
                        update={"SiegLoopStrategy": strategy}
                    )
                }
            )
        )
    with pytest.raises(ValueError, match="LwtControl"):
        check_sieg_loop_strategy(
            ops.model_copy(
                update={
                    "FamilyParams": ops.FamilyParams.model_copy(
                        update={"SiegLoopStrategy": SiegLoopStrategy.LwtControl}
                    )
                }
            )
        )


def declare_twin(d: dict, name: str = "hp-idu", handle: str | None = "auto.hp-boss.hp-idu") -> None:
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
                "Version": "303",
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
                n["Handle"] = "auto.hp-boss.hp-odu"
    reject(assembled, stray_leaf, "Axiom 14")


def test_gw_house0_layout_axiom_16_dangling_board(assembled: dict) -> None:
    """An i2c relay's BoardComponentId must resolve to a board component."""

    def dangle(d: dict) -> None:
        for c in d["Components"]:
            if c["TypeName"] == "i2c.relay.component.gt":
                c["BoardComponentId"] = "00000000-0000-4000-8000-000000000000"

    reject(assembled, dangle, "Axiom 16")


def test_gw_house0_layout_axiom_16_unknown_dac_name(assembled: dict) -> None:
    """A DAC output's DacName must be one the board record offers."""

    def rename(d: dict) -> None:
        for c in d["Components"]:
            if c["TypeName"] == "i2c.dac.output.component.gt":
                c["DacName"] = "NoSuchDac"

    reject(assembled, rename, "Axiom 16")


def test_gw_house0_layout_axiom_17_missing_depth_channel(assembled: dict) -> None:
    def drop(d: dict) -> None:
        for key in ("DataChannels", "DerivedChannels"):
            d[key] = [c for c in d[key] if c["Name"] != "buffer-depth2"]

    reject(assembled, drop, "Axiom 17")


def test_gw_house0_layout_axiom_18_unknown_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        d["Hydronic"]["Zones"][0]["TempChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 18")


def test_gw_house0_layout_axiom_18_not_a_temperature(assembled: dict) -> None:
    def point_at_power(d: dict) -> None:
        d["Hydronic"]["Zones"][0]["TempChannelName"] = "hp-odu-pwr"

    reject(assembled, point_at_power, "Axiom 18")


def test_gw_house0_layout_axiom_19_unknown_whitewire_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        circuit = d["Hydronic"]["ZoneCallCircuits"][0]
        for c in d["DerivedChannels"]:
            if c["InputChannelNames"] == [circuit["WhitewireChannelName"]]:
                c["InputChannelNames"] = ["no-such-channel"]
        circuit["WhitewireChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 19")


def test_gw_house0_layout_axiom_4_missing_heat_call(assembled: dict) -> None:
    def drop(d: dict) -> None:
        whitewire = d["Hydronic"]["ZoneCallCircuits"][0]["WhitewireChannelName"]
        d["DerivedChannels"] = [
            c
            for c in d["DerivedChannels"]
            if not (c["Strategy"] == "heat-call" and c["InputChannelNames"] == [whitewire])
        ]

    reject(assembled, drop, "Axiom 4")


def test_gw_house0_layout_axiom_4_second_heat_call(assembled: dict) -> None:
    def duplicate(d: dict) -> None:
        whitewire = d["Hydronic"]["ZoneCallCircuits"][0]["WhitewireChannelName"]
        heat_call = next(
            c
            for c in d["DerivedChannels"]
            if c["Strategy"] == "heat-call" and c["InputChannelNames"] == [whitewire]
        )
        d["DerivedChannels"].append(
            {**heat_call, "Name": heat_call["Name"] + "-again", "Id": str(uuid.uuid4())}
        )

    reject(assembled, duplicate, "Axiom 4")


# Channel integrity axioms. Earlier axioms pin the channels with these
# Strategies by name or by input, so the mutations below use the others and
# trip only the axiom under test. Matches are anchored at the opening
# parenthesis so "Axiom 2" cannot be satisfied by "Axiom 20".
PINNED_STRATEGIES = {"transactive-power", "heat-call", "system-model"}


def free_derived(d: dict) -> list[dict]:
    return [c for c in d["DerivedChannels"] if c["Strategy"] not in PINNED_STRATEGIES]


def no_actor_node_name(d: dict) -> str:
    return next(n["Name"] for n in d["ShNodes"] if n["ActorClass"] == "NoActor")


def add_derived_copy(d: dict, name: str) -> None:
    d["DerivedChannels"].append(
        {**free_derived(d)[-1], "Name": name, "Id": str(uuid.uuid4())}
    )


def test_gw_house0_layout_axiom_20_a_creator_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 20 \(.*failed \(a\)")


def test_gw_house0_layout_axiom_20_b_creator_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 20 \(.*failed \(b\)")


def test_gw_house0_layout_axiom_21_a_about_node_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["AboutNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(a\)")


def test_gw_house0_layout_axiom_21_b_capturer_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(b\)")


def test_gw_house0_layout_axiom_21_c_capturer_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(c\)")


def test_gw_house0_layout_axiom_22_a_input_is_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["InputChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 22 \(.*failed \(a\)")


def test_gw_house0_layout_axiom_22_b_self_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        channel = free_derived(d)[-1]
        channel["InputChannelNames"] = [channel["Name"]]

    reject(assembled, mutate, r"Axiom 22 \(.*failed \(b\)")


def test_gw_house0_layout_axiom_22_b_two_channel_cycle(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]
        second["InputChannelNames"] = [first["Name"]]

    reject(assembled, mutate, r"Axiom 22 \(.*failed \(b\)")


def test_gw_house0_layout_axiom_22_derived_input_chain_accepted(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]

    House0Layout.model_validate(mutated(assembled, mutate))


def test_gw_house0_layout_axiom_23_derived_shares_a_data_channel_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, d["DataChannels"][-1]["Name"])

    reject(assembled, mutate, r"Axiom 23 \(")


def test_gw_house0_layout_axiom_23_two_derived_share_a_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, free_derived(d)[-1]["Name"])

    reject(assembled, mutate, r"Axiom 23 \(")


def drop_channel(d: dict, name: str) -> None:
    d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != name]
    d["DerivedChannels"] = [c for c in d["DerivedChannels"] if c["Name"] != name]


def first_circuit(d: dict) -> dict:
    return d["Hydronic"]["ZoneCallCircuits"][0]


def test_gw_house0_layout_axiom_24_missing_tank_depth(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_channel(d, "tank1-depth1")

    reject(assembled, mutate, r"Axiom 24 \(")


def test_gw_house0_layout_axiom_25_web_server_node_absent(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        for node in d["ShNodes"]:
            if node["Name"] == "web-server":
                node["Name"] = "web-server2"

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_house0_layout_axiom_26_a_slab_circuit_without_a_floor_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit.pop("FloorTempChannelName", None)

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_house0_layout_axiom_26_b_floor_channel_does_not_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "no-such-channel"

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_house0_layout_axiom_26_b_floor_channel_is_not_a_temperature(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "dist-flow"

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_house0_layout_axiom_26_slab_circuit_with_a_temperature_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit["FloorTempChannelName"] = "dist-swt"

    House0Layout.model_validate(mutated(assembled, mutate))


def test_gw_house0_layout_axiom_27_disabled_node_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = ["no-such-node"]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_layout_axiom_27_disabled_channel_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_layout_axiom_28_disabled_node_captures_nothing(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [no_actor_node_name(d)]

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_house0_layout_axiom_28_captured_channel_not_listed(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [sensor_off_the_meter(d)]
        d["DisabledChannelNames"] = []

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_house0_layout_axiom_28_disabled_node_with_its_channels(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        node = sensor_off_the_meter(d)
        captured = [c["Name"] for c in d["DataChannels"] if c["CapturedByNodeName"] == node]
        derived = [c["Name"] for c in d["DerivedChannels"] if set(c["InputChannelNames"]) & set(captured)]
        d["DisabledNodeNames"] = [node]
        d["DisabledChannelNames"] = captured + derived

    House0Layout.model_validate(mutated(assembled, mutate))


def test_gw_house0_layout_axiom_29_enabled_derived_reads_disabled_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        derived = unmetered_derived(d)
        d["DisabledChannelNames"] = [derived["InputChannelNames"][0]]

    reject(assembled, mutate, r"Axiom 29 \(")


def test_gw_house0_layout_axiom_29_disabled_derived_may_read_disabled_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        derived = unmetered_derived(d)
        disabled = [derived["InputChannelNames"][0], derived["Name"]]
        # a derived channel downstream of a disabled one is disabled with it
        grew = True
        while grew:
            grew = False
            for c in d["DerivedChannels"]:
                if c["Name"] not in disabled and set(c["InputChannelNames"]) & set(disabled):
                    disabled.append(c["Name"])
                    grew = True
        d["DisabledChannelNames"] = disabled

    House0Layout.model_validate(mutated(assembled, mutate))

def test_gw_house0_layout_axiom_30_a_actuator_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != "vdc-relay"]

    reject(assembled, mutate, r"Axiom 30 \(")


def test_gw_house0_layout_axiom_30_a_actuator_channel_about_another_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        next(c for c in d["DataChannels"] if c["Name"] == "vdc-relay")["AboutNodeName"] = "hp-scada-ops-relay"

    reject(assembled, mutate, r"Axiom 30 \(")


def test_gw_house0_layout_axiom_30_a_circuit_relay_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        relay = d["Hydronic"]["ZoneCallCircuits"][0]["OpsRelayNode"]
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != relay]

    reject(assembled, mutate, r"Axiom 30 \(")


@pytest.mark.parametrize(
    ("name", "telemetry", "quantity"),
    [("vdc-relay", "VoltsTimesTen", "Voltage"), ("dist-010v", "RelayState", "Unitless")],
)
def test_gw_house0_layout_axiom_30_b_actuator_channel_telemetry(
    assembled: dict, name: str, telemetry: str, quantity: str
) -> None:
    """The quantity moves with the telemetry so data.channel.gt's own
    consistency check is not what fires."""

    def mutate(d: dict) -> None:
        channel = next(c for c in d["DataChannels"] if c["Name"] == name)
        channel["TelemetryName"] = telemetry
        channel["Quantity"] = quantity

    reject(assembled, mutate, r"Axiom 30 \(")



def drop_nodes(names: set[str]):
    """Drop nodes with the components they bind, so ComponentBinding stays quiet."""

    def mutate(d: dict) -> None:
        component_ids = {n.get("ComponentId") for n in d["ShNodes"] if n["Name"] in names}
        d["ShNodes"] = [n for n in d["ShNodes"] if n["Name"] not in names]
        d["Components"] = [c for c in d["Components"] if c["ComponentId"] not in component_ids]

    return mutate


def test_gw_house0_layout_axiom_31_scada_owner_without_primary_010v(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_nodes({"primary-010v"})(d)
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != "primary-010v"]

    reject(assembled, mutate, r"Axiom 31 \(")


def test_gw_house0_layout_axiom_31_scada_owner_relay_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"] = [
            c for c in d["DataChannels"] if c["Name"] != "primary-pump-failsafe-relay"
        ]

    reject(assembled, mutate, r"Axiom 31 \(")


def test_gw_house0_layout_axiom_31_heat_pump_owner_with_primary_pump_actuators(
    assembled: dict,
) -> None:
    def mutate(d: dict) -> None:
        d["Hydronic"]["PrimaryPumpOwner"] = "HeatPump"

    reject(assembled, mutate, r"Axiom 31 \(")


def test_gw_house0_layout_axiom_31_heat_pump_owner_without_actuators_is_accepted(
    assembled: dict,
) -> None:
    names = {"primary-pump-failsafe-relay", "primary-pump-scada-ops-relay", "primary-010v"}

    def mutate(d: dict) -> None:
        d["Hydronic"]["PrimaryPumpOwner"] = "HeatPump"
        drop_nodes(names)(d)
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] not in names]

    House0Layout.model_validate(mutated(assembled, mutate))


def hp_record(device_type: str, factory_installed: bool, overridable: bool) -> dict:
    return {
        "TypeName": "hp.device.type.gt",
        "Version": "000",
        "DeviceType": device_type,
        "DisplayName": "test record",
        "MaxKwEl": 6.0,
        "HeatingCapacityBtuHr": 48000,
        "CoolingCapacityBtuHr": 48000,
        "PrimaryPumpFactoryInstalled": factory_installed,
        "PrimaryPumpOverridable": overridable,
        "PrimaryPumpAlwaysOn": False,
        "Refrigerant": "R32",
        "CompressorRatedAmps": 20.0,
        "Mca": 30.0,
        "Mop": 40.0,
        "ProductInfoUrl": "https://example.com",
    }


def odu_device_type(d: dict) -> str:
    odu = next(n for n in d["ShNodes"] if n["Name"] == "hp-odu")
    return next(c for c in d["Components"] if c["ComponentId"] == odu["ComponentId"])["DeviceType"]


def test_gw_house0_layout_axiom_32_scada_owner_against_a_non_overridable_factory_pump(
    assembled: dict,
) -> None:
    def mutate(d: dict) -> None:
        d["DeviceTypes"].append(hp_record(odu_device_type(d), True, False))

    reject(assembled, mutate, r"Axiom 32 \(")


def test_gw_house0_layout_axiom_32_scada_owner_against_an_overridable_factory_pump_is_accepted(
    assembled: dict,
) -> None:
    def mutate(d: dict) -> None:
        d["DeviceTypes"].append(hp_record(odu_device_type(d), True, True))

    House0Layout.model_validate(mutated(assembled, mutate))


def test_gw_house0_layout_axiom_6_transactive_input_disabled(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        transactive = next(c for c in d["DerivedChannels"] if c["Strategy"] == "transactive-power")
        d["DisabledChannelNames"] = [transactive["InputChannelNames"][0]]

    reject(assembled, mutate, r"Axiom 6 \(")


def test_gw_house0_layout_axiom_28_disabled_actuator_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = ["store-pump-relay"]
        d["DisabledChannelNames"] = ["store-pump-relay"]

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_house0_layout_axiom_28_disabled_actuator_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledChannelNames"] = ["store-pump-relay"]

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_house0_layout_axiom_34_heat_call_for_no_circuit(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        stray = json.loads(json.dumps(
            next(c for c in d["DerivedChannels"] if c["Strategy"] == "heat-call")
        ))
        stray["Name"] = "stray-heat-call"
        stray["Id"] = str(uuid.uuid4())
        stray["InputChannelNames"] = ["hp-odu-pwr"]
        d["DerivedChannels"].append(stray)

    reject(assembled, mutate, r"Axiom 34 \(")


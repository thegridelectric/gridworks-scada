"""Rejecting tests for gw.house0.no.sieg/000's axioms, on the hazel sim pair.

Each counterexample is a typed mutation of the assembled fixture pair,
re-validated at the boundary — chosen so the intended axiom fires. The word
is gw.house0.layout without the Siegenthaler loop and with the secondary
pump: the shared axioms are tested as there, the ones that differ (3, 5, 7,
9, 13, 32) on the sieg-less surface, and 38 on the circulators' running channels."""

import json
import uuid
from pathlib import Path

import pytest

from gwsproto.named_types import House0NoSiegLayout, OperationalParams
from sema_to_dc import assemble_runtime_layout
from tests.named_types.sema_oracle import assert_refused

CONFIG = Path(__file__).parent.parent / "config"


PAIRS = {
    "no-sieg-hazel": (
        "gw.house0.no.sieg.hazel.layout.json",
        "gw.house0.no.sieg.hazel.operational.params.json",
    ),
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
    assert_refused(House0NoSiegLayout, mutated(assembled, mutate), match=axiom)

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



def test_gw_house0_no_sieg_layout_generated(assembled: dict) -> None:
    House0NoSiegLayout.model_validate(assembled)


def test_gw_house0_no_sieg_axiom_2(assembled: dict) -> None:
    """derived-generator with the wrong ActorClass fails the core pair check."""
    def mutate(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "derived-generator":
                n["ActorClass"] = "NoActor"
                n.pop("ActorHierarchyName", None)
    reject(assembled, mutate, "Axiom 2")


def test_gw_house0_no_sieg_axiom_2_cold_watch(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(ShNodes=[n for n in d["ShNodes"] if n["Name"] != "cold-watch"]),
        "Axiom 2",
    )


def test_gw_house0_no_sieg_axiom_3(assembled: dict) -> None:
    """hp-boss is an unconditional command node — removing it fails."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "hp-boss"]
        ),
        "Axiom 3",
    )


def test_gw_house0_no_sieg_axiom_3_sieg_loop_is_not_required(assembled: dict) -> None:
    """The word stops requiring the loop; a sieg-loop node is not forbidden
    either, but the fixture has none and the axiom holds without it."""
    assert not any(n["Name"] == "sieg-loop" for n in assembled["ShNodes"])
    House0NoSiegLayout.model_validate(assembled)


def set_handle(name: str, handle: str):
    def mutate(d: dict) -> None:
        next(n for n in d["ShNodes"] if n["Name"] == name)["Handle"] = handle
    return mutate


def test_gw_house0_no_sieg_axiom_9_secondary_pump_hack_relay(assembled: dict) -> None:
    """The relay whose contacts the pump's feed still passes through is required."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "secondary-pump-hack-relay"]
        ),
        "Axiom 9",
    )


def test_gw_house0_no_sieg_axiom_32_hack_relay_declared_flat(assembled: dict) -> None:
    """The hack relay is hp-boss's fixed relay, as the pump relay is."""
    reject(assembled, set_handle("secondary-pump-hack-relay", "auto.secondary-pump-hack-relay"), "Axiom 32")


def test_gw_house0_no_sieg_axiom_32_command_node_declared_under_lc(assembled: dict) -> None:
    """hp-boss and its relay move together so the tree stays prefix-closed
    and the handle axiom is the one that rejects."""
    def mutate(d: dict) -> None:
        set_handle("hp-boss", "auto.lc.n.hp-boss")(d)
        set_handle("hp-scada-ops-relay", "auto.lc.n.hp-boss.hp-scada-ops-relay")(d)
        set_handle("secondary-pump-relay", "auto.lc.n.hp-boss.secondary-pump-relay")(d)
        set_handle("secondary-pump-hack-relay", "auto.lc.n.hp-boss.secondary-pump-hack-relay")(d)
    reject(assembled, mutate, "Axiom 32")


def test_gw_house0_no_sieg_axiom_32_fixed_relay_declared_flat(assembled: dict) -> None:
    """The secondary pump is hp-boss's fixed relay, as the call relay is."""
    reject(assembled, set_handle("secondary-pump-relay", "auto.secondary-pump-relay"), "Axiom 32")


def test_gw_house0_no_sieg_axiom_32_floating_actuator_under_a_boss(assembled: dict) -> None:
    reject(assembled, set_handle("store-pump-relay", "auto.lc.n.store-pump-relay"), "Axiom 32")


def test_gw_house0_no_sieg_axiom_7(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(
            DataChannels=[c for c in d["DataChannels"] if c["Name"] != "store-flow"]
        ),
        "Axiom 7",
    )


def test_gw_house0_no_sieg_axiom_7_secondary_surface(assembled: dict) -> None:
    """The house side of the heat exchanger is required sensing."""
    for name in ("secondary-flow", "secondary-lwt", "secondary-ewt", "secondary-pump-pwr"):
        reject(
            assembled,
            lambda d, name=name: d.update(
                DataChannels=[c for c in d["DataChannels"] if c["Name"] != name]
            ),
            "Axiom 7",
        )


def test_gw_house0_no_sieg_axiom_5_derived_sieg_sum(assembled: dict) -> None:
    """A sieg-less plant measures primary-flow: there is no loop to sum."""
    reject(
        assembled,
        lambda d: d["Hydronic"].update(PrimaryFlowSource="DerivedSiegSum"),
        r"Axiom 5 \(",
    )


def test_gw_house0_no_sieg_axiom_1_duplicate_id(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["ShNodes"][1]["ShNodeId"] = d["ShNodes"][0]["ShNodeId"]

    reject(assembled, mutate, r"Axiom 1 \(")


def test_gw_house0_no_sieg_axiom_6(assembled: dict) -> None:
    """A transactive input whose about-node loses NameplatePowerW fails."""
    def mutate(d: dict) -> None:
        tx = [c for c in d["DerivedChannels"] if c.get("Strategy") == "transactive-power"][0]
        about = {c["Name"]: c["AboutNodeName"] for c in d["DataChannels"]}[tx["InputChannelNames"][0]]
        for n in d["ShNodes"]:
            if n["Name"] == about:
                n.pop("NameplatePowerW", None)
    reject(assembled, mutate, "Axiom 6")


def test_gw_house0_no_sieg_axiom_8(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(
            DerivedChannels=[c for c in d["DerivedChannels"] if c["Name"] != "usable-energy"]
        ),
        "Axiom 8",
    )


def test_gw_house0_no_sieg_axiom_14(assembled: dict) -> None:
    """Every component is HAD by exactly one ShNode: an orphan component
    (its node dropped its ComponentId) is rejected. The web server has no
    other axiom guarding it, so axiom 15 itself fires."""

    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "web-server":
                n.pop("ComponentId")

    reject(assembled, orphan, "Axiom 14")


def test_gw_house0_no_sieg_axiom_9_relay(assembled: dict) -> None:
    """The aquastat control relay is a required plant relay."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "aquastat-ctrl-relay"]
        ),
        "Axiom 9",
    )


def test_gw_house0_no_sieg_axiom_9_secondary_pump_relay(assembled: dict) -> None:
    """The secondary pump's relay is a required plant relay."""
    reject(
        assembled,
        lambda d: d.update(
            ShNodes=[n for n in d["ShNodes"] if n["Name"] != "secondary-pump-relay"]
        ),
        "Axiom 9",
    )


def test_gw_house0_no_sieg_axiom_9_output(assembled: dict) -> None:
    """A 0-10V output with the wrong ActorClass fails clause a."""

    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "store-010v":
                n["ActorClass"] = "NoActor"
                n.pop("ActorHierarchyName", None)

    reject(assembled, reclass, "Axiom 9")


def test_gw_house0_no_sieg_axiom_9_output_component(assembled: dict) -> None:
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

    reject(assembled, rebind, "Axiom 9")


def test_gw_house0_no_sieg_axiom_9_circuits(assembled: dict) -> None:
    """An empty circuit list is refused by the hydronic block, where every
    zone names a primary circuit."""
    reject(
        assembled,
        lambda d: d["Hydronic"].update(ZoneCallCircuits=[]),
        r"Axiom 3 \(PrimaryCircuit",
    )


def test_gw_house0_no_sieg_axiom_10_component(assembled: dict) -> None:
    """hp-odu is equipment: it carries a component."""

    def unbind(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n.pop("ComponentId")

    reject(assembled, unbind, "Axiom 10")


def test_gw_house0_no_sieg_axiom_10_actor_class(assembled: dict) -> None:
    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["ActorClass"] = "Relay"
                n["ActorHierarchyName"] = "s.hp-odu"

    reject(assembled, reclass, "Axiom 10")


def declare_twin(d: dict, name: str = "hp-odu", handle: str | None = "auto.hp-boss.hp-odu") -> None:
    d["Hydronic"]["HpCommandNodeName"] = name
    for n in d["ShNodes"]:
        if n["Name"] == name:
            n["ActorClass"] = "HpTwin"
            n["ActorHierarchyName"] = f"s.{name}"
            if handle is not None:
                n["Handle"] = handle


def test_gw_house0_no_sieg_axiom_11_declared_twin_accepted(assembled: dict) -> None:
    """A declared hp-odu twin under hp-boss satisfies both clauses."""
    House0NoSiegLayout.model_validate(mutated(assembled, declare_twin))


def test_gw_house0_no_sieg_axiom_11_a_no_actor(assembled: dict) -> None:
    """Declared but left NoActor."""
    def declare_only(d: dict) -> None:
        d["Hydronic"]["HpCommandNodeName"] = "hp-odu"
    reject(assembled, declare_only, "Axiom 11")


def test_gw_house0_no_sieg_axiom_11_a_wrong_parent(assembled: dict) -> None:
    """The twin must hang directly under hp-boss."""
    reject(assembled, lambda d: declare_twin(d, handle="auto.lc.n.hp-odu"), "Axiom 11")


def test_gw_house0_no_sieg_axiom_11_a_unknown_name(assembled: dict) -> None:
    """hp-ctrl-box is a legal target name but a House0 layout has no such node."""
    def declare_missing(d: dict) -> None:
        d["Hydronic"]["HpCommandNodeName"] = "hp-ctrl-box"
    reject(assembled, declare_missing, "Axiom 11")


def test_gw_house0_no_sieg_axiom_11_b_undeclared_twin(assembled: dict) -> None:
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
    reject(assembled, stray_twin, "Axiom 11")


def test_gw_house0_no_sieg_axiom_12(assembled: dict) -> None:
    """A relay handle whose parent names no ShNode is an orphan."""
    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n["Handle"] = "auto.nobody.vdc-relay"
    reject(assembled, orphan, "Axiom 12")


def test_gw_house0_no_sieg_axiom_13_a(assembled: dict) -> None:
    """An actuator with a bare Name for a handle has no boss."""
    def undotted(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n.pop("Handle", None)
    reject(assembled, undotted, "Axiom 13")


def test_gw_house0_no_sieg_axiom_13_b(assembled: dict) -> None:
    """hp-odu (NoActor) given a handle under hp-boss is a leaf that is
    neither actuator nor command node."""
    def stray_leaf(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["Handle"] = "auto.hp-boss.hp-odu"
    reject(assembled, stray_leaf, "Axiom 13")


def test_gw_house0_no_sieg_axiom_15_dangling_board(assembled: dict) -> None:
    """An i2c relay's BoardComponentId must resolve to a board component."""

    def dangle(d: dict) -> None:
        for c in d["Components"]:
            if c["TypeName"] == "i2c.relay.component.gt":
                c["BoardComponentId"] = "00000000-0000-4000-8000-000000000000"

    reject(assembled, dangle, "Axiom 15")


def test_gw_house0_no_sieg_axiom_15_unknown_dac_name(assembled: dict) -> None:
    """A DAC output's DacName must be one the board record offers."""

    def rename(d: dict) -> None:
        for c in d["Components"]:
            if c["TypeName"] == "i2c.dac.output.component.gt":
                c["DacName"] = "NoSuchDac"

    reject(assembled, rename, "Axiom 15")


def test_gw_house0_no_sieg_axiom_16_missing_depth_channel(assembled: dict) -> None:
    def drop(d: dict) -> None:
        for key in ("DataChannels", "DerivedChannels"):
            d[key] = [c for c in d[key] if c["Name"] != "buffer-depth2"]

    reject(assembled, drop, "Axiom 16")


def test_gw_house0_no_sieg_axiom_17_unknown_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        d["Hydronic"]["ZoneCallCircuits"][0]["TempChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 17")


def test_gw_house0_no_sieg_axiom_17_not_a_temperature(assembled: dict) -> None:
    def point_at_power(d: dict) -> None:
        d["Hydronic"]["ZoneCallCircuits"][0]["TempChannelName"] = "hp-odu-pwr"

    reject(assembled, point_at_power, "Axiom 17")


def test_gw_house0_no_sieg_axiom_18_unknown_whitewire_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        circuit = d["Hydronic"]["ZoneCallCircuits"][0]
        for c in d["DerivedChannels"]:
            if c["InputChannelNames"] == [circuit["WhitewireChannelName"]]:
                c["InputChannelNames"] = ["no-such-channel"]
        circuit["WhitewireChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 18")


def test_gw_house0_no_sieg_axiom_4_missing_heat_call(assembled: dict) -> None:
    def drop(d: dict) -> None:
        whitewire = d["Hydronic"]["ZoneCallCircuits"][0]["WhitewireChannelName"]
        d["DerivedChannels"] = [
            c
            for c in d["DerivedChannels"]
            if not (c["Strategy"] == "heat-call" and c["InputChannelNames"] == [whitewire])
        ]

    reject(assembled, drop, "Axiom 4")


def test_gw_house0_no_sieg_axiom_4_second_heat_call(assembled: dict) -> None:
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
# parenthesis so "Axiom 2" cannot be satisfied by "Axiom 19".
PINNED_STRATEGIES = {
    "transactive-power", "heat-call", "system-model", "simple-falling-edge-setpoint",
    "circulator-running",
}


def free_derived(d: dict) -> list[dict]:
    return [c for c in d["DerivedChannels"] if c["Strategy"] not in PINNED_STRATEGIES]


def no_actor_node_name(d: dict) -> str:
    return next(n["Name"] for n in d["ShNodes"] if n["ActorClass"] == "NoActor")


def add_derived_copy(d: dict, name: str) -> None:
    d["DerivedChannels"].append(
        {**free_derived(d)[-1], "Name": name, "Id": str(uuid.uuid4())}
    )


def test_gw_house0_no_sieg_axiom_19_a_creator_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 19 \(.*failed \(a\)")


def test_gw_house0_no_sieg_axiom_19_b_creator_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 19 \(.*failed \(b\)")


def test_gw_house0_no_sieg_axiom_20_a_about_node_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["AboutNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 20 \(.*failed \(a\)")


def test_gw_house0_no_sieg_axiom_20_b_capturer_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 20 \(.*failed \(b\)")


def test_gw_house0_no_sieg_axiom_20_c_capturer_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 20 \(.*failed \(c\)")


def test_gw_house0_no_sieg_axiom_21_a_input_is_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["InputChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(a\)")


def test_gw_house0_no_sieg_axiom_21_b_self_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        channel = free_derived(d)[-1]
        channel["InputChannelNames"] = [channel["Name"]]

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(b\)")


def test_gw_house0_no_sieg_axiom_21_b_two_channel_cycle(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]
        second["InputChannelNames"] = [first["Name"]]

    reject(assembled, mutate, r"Axiom 21 \(.*failed \(b\)")


def test_gw_house0_no_sieg_axiom_21_derived_input_chain_accepted(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]

    House0NoSiegLayout.model_validate(mutated(assembled, mutate))


def test_gw_house0_no_sieg_axiom_22_derived_shares_a_data_channel_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, d["DataChannels"][-1]["Name"])

    reject(assembled, mutate, r"Axiom 22 \(")


def test_gw_house0_no_sieg_axiom_22_two_derived_share_a_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, free_derived(d)[-1]["Name"])

    reject(assembled, mutate, r"Axiom 22 \(")


def drop_channel(d: dict, name: str) -> None:
    d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != name]
    d["DerivedChannels"] = [c for c in d["DerivedChannels"] if c["Name"] != name]


def first_circuit(d: dict) -> dict:
    return d["Hydronic"]["ZoneCallCircuits"][0]


def test_gw_house0_no_sieg_axiom_23_missing_tank_depth(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_channel(d, "tank1-depth1")

    reject(assembled, mutate, r"Axiom 23 \(")


def test_gw_house0_no_sieg_axiom_24_web_server_node_absent(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        for node in d["ShNodes"]:
            if node["Name"] == "web-server":
                node["Name"] = "web-server2"

    reject(assembled, mutate, r"Axiom 24 \(")


def test_gw_house0_no_sieg_axiom_25_a_slab_circuit_without_a_floor_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit.pop("FloorTempChannelName", None)

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_house0_no_sieg_axiom_25_b_floor_channel_does_not_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "no-such-channel"

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_house0_no_sieg_axiom_25_b_floor_channel_is_not_a_temperature(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "dist-flow"

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_house0_no_sieg_axiom_25_slab_circuit_with_a_temperature_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit["FloorTempChannelName"] = "dist-swt"

    House0NoSiegLayout.model_validate(mutated(assembled, mutate))


def test_gw_house0_no_sieg_axiom_26_disabled_node_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = ["no-such-node"]

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_house0_no_sieg_axiom_26_disabled_channel_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_house0_no_sieg_axiom_27_disabled_node_captures_nothing(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [no_actor_node_name(d)]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_no_sieg_axiom_27_captured_channel_not_listed(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [sensor_off_the_meter(d)]
        d["DisabledChannelNames"] = []

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_no_sieg_axiom_27_disabled_node_with_its_channels(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        node = sensor_off_the_meter(d)
        captured = [c["Name"] for c in d["DataChannels"] if c["CapturedByNodeName"] == node]
        derived = [c["Name"] for c in d["DerivedChannels"] if set(c["InputChannelNames"]) & set(captured)]
        d["DisabledNodeNames"] = [node]
        d["DisabledChannelNames"] = captured + derived

    House0NoSiegLayout.model_validate(mutated(assembled, mutate))


def test_gw_house0_no_sieg_axiom_28_enabled_derived_reads_disabled_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        derived = unmetered_derived(d)
        d["DisabledChannelNames"] = [derived["InputChannelNames"][0]]

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_house0_no_sieg_axiom_28_disabled_derived_may_read_disabled_input(assembled: dict) -> None:
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

    House0NoSiegLayout.model_validate(mutated(assembled, mutate))

def test_gw_house0_no_sieg_axiom_29_a_actuator_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != "vdc-relay"]

    reject(assembled, mutate, r"Axiom 29 \(")


def test_gw_house0_no_sieg_axiom_29_a_actuator_channel_about_another_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        next(c for c in d["DataChannels"] if c["Name"] == "vdc-relay")["AboutNodeName"] = "hp-scada-ops-relay"

    reject(assembled, mutate, r"Axiom 29 \(")


def test_gw_house0_no_sieg_axiom_29_a_circuit_relay_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        relay = d["Hydronic"]["ZoneCallCircuits"][0]["OpsRelayNode"]
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != relay]

    reject(assembled, mutate, r"Axiom 29 \(")


@pytest.mark.parametrize(
    ("name", "telemetry", "quantity"),
    [("vdc-relay", "VoltsTimesTen", "Voltage"), ("dist-010v", "RelayState", "Unitless")],
)
def test_gw_house0_no_sieg_axiom_29_b_actuator_channel_telemetry(
    assembled: dict, name: str, telemetry: str, quantity: str
) -> None:
    """The quantity moves with the telemetry so data.channel.gt's own
    consistency check is not what fires."""

    def mutate(d: dict) -> None:
        channel = next(c for c in d["DataChannels"] if c["Name"] == name)
        channel["TelemetryName"] = telemetry
        channel["Quantity"] = quantity

    reject(assembled, mutate, r"Axiom 29 \(")



def drop_nodes(names: set[str]):
    """Drop nodes with the components they bind, so ComponentBinding stays quiet."""

    def mutate(d: dict) -> None:
        component_ids = {n.get("ComponentId") for n in d["ShNodes"] if n["Name"] in names}
        d["ShNodes"] = [n for n in d["ShNodes"] if n["Name"] not in names]
        d["Components"] = [c for c in d["Components"] if c["ComponentId"] not in component_ids]

    return mutate


def test_gw_house0_no_sieg_axiom_30_scada_owner_without_actuators(assembled: dict) -> None:
    """Hazel's heat pump runs the primary pump (elm's shape); handing the pump
    to the scada without its three actuators is refused."""
    def mutate(d: dict) -> None:
        d["Hydronic"]["PrimaryPumpOwner"] = "Scada"

    reject(assembled, mutate, r"Axiom 30 \(")


def test_gw_house0_no_sieg_axiom_30_heat_pump_owner_with_a_primary_pump_node(
    assembled: dict,
) -> None:
    """Under HeatPump none of the primary-pump actuator names exists as a node."""
    def mutate(d: dict) -> None:
        d["ShNodes"].append(
            {
                "ShNodeId": str(uuid.uuid4()),
                "Name": "primary-pump-scada-ops-relay",
                "ActorClass": "NoActor",
                "DisplayName": "stray primary pump relay name",
            }
        )

    reject(assembled, mutate, r"Axiom 30 \(")


def test_gw_house0_no_sieg_axiom_30_heat_pump_owner_without_actuators_is_accepted(
    assembled: dict,
) -> None:
    names = {"primary-pump-failsafe-relay", "primary-pump-scada-ops-relay", "primary-010v"}
    assert assembled["Hydronic"]["PrimaryPumpOwner"] == "HeatPump"
    assert not names & {n["Name"] for n in assembled["ShNodes"]}
    House0NoSiegLayout.model_validate(assembled)


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


def test_gw_house0_no_sieg_record_agreement_binds_the_scada_owner_only(
    assembled: dict,
) -> None:
    """The record agreement binds the Scada owner only: a monobloc whose
    factory pump the scada cannot override is fine when the unit runs it.
    (The rejecting case needs the Scada owner's actuators, which hazel does
    not have; gw.house0.layout's orange pair tests it.)"""
    def mutate(d: dict) -> None:
        d["DeviceTypes"].append(hp_record(odu_device_type(d), True, False))

    House0NoSiegLayout.model_validate(mutated(assembled, mutate))


def test_gw_house0_no_sieg_axiom_6_transactive_input_disabled(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        transactive = next(c for c in d["DerivedChannels"] if c["Strategy"] == "transactive-power")
        d["DisabledChannelNames"] = [transactive["InputChannelNames"][0]]

    reject(assembled, mutate, r"Axiom 6 \(")


def test_gw_house0_no_sieg_axiom_27_disabled_actuator_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = ["store-pump-relay"]
        d["DisabledChannelNames"] = ["store-pump-relay"]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_no_sieg_axiom_27_disabled_actuator_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledChannelNames"] = ["store-pump-relay"]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_house0_no_sieg_axiom_33_heat_call_for_no_circuit(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        stray = json.loads(json.dumps(
            next(c for c in d["DerivedChannels"] if c["Strategy"] == "heat-call")
        ))
        stray["Name"] = "stray-heat-call"
        stray["Id"] = str(uuid.uuid4())
        stray["InputChannelNames"] = ["hp-odu-pwr"]
        d["DerivedChannels"].append(stray)

    reject(assembled, mutate, r"Axiom 33 \(")


def test_gw_house0_no_sieg_axiom_34_unknown_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        d["Hydronic"]["ZoneCallCircuits"][0]["SetpointChannelName"] = "no-such-channel"

    reject(assembled, rename, r"Axiom 34 \(")


def test_gw_house0_no_sieg_axiom_34_learned_setpoint_wrong_strategy(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        name = d["Hydronic"]["ZoneCallCircuits"][0]["SetpointChannelName"]
        next(c for c in d["DerivedChannels"] if c["Name"] == name)["Strategy"] = "identity"

    reject(assembled, mutate, r"Axiom 34 \(")


def test_gw_house0_no_sieg_axiom_35_setpoint_not_read_from_the_thermostat(assembled: dict) -> None:
    """A circuit declared FromThermostat whose setpoint channel is not a
    data channel captured by its thermostat's node."""
    def mutate(d: dict) -> None:
        circuit = d["Hydronic"]["ZoneCallCircuits"][0]
        circuit["SetpointSource"] = "FromThermostat"
        circuit["Thermostat"]["Kind"] = "HoneywellViaHubitat"
        circuit["Thermostat"]["ComponentId"] = str(uuid.uuid4())

    reject(assembled, mutate, r"Axiom 35 \(")


def test_gw_house0_no_sieg_axiom_36(assembled: dict) -> None:
    """A House0 home stores heat in water tanks."""
    reject(assembled, lambda d: d["Hydronic"].pop("WaterStore"), r"Axiom 36 \(WaterStore\)")


def test_gw_house0_no_sieg_axiom_3_cold_override(assembled: dict) -> None:
    """cold-override is a command node in every House0 layout."""
    def mutate(d: dict) -> None:
        d["ShNodes"] = [n for n in d["ShNodes"] if n["Name"] != "cold-override"]

    reject(assembled, mutate, r"Axiom 3 \(")


def test_gw_house0_no_sieg_axiom_3_c_backup_node_without_a_backup(assembled: dict) -> None:
    reject(assembled, lambda d: d["Hydronic"].pop("Backup"), r"Axiom 3 \(")


def test_gw_house0_no_sieg_axiom_37(assembled: dict) -> None:
    """A boiler relay that is not a Relay ShNode."""
    def mutate(d: dict) -> None:
        d["Hydronic"]["Backup"]["AquastatCtrlRelayName"] = "backup"

    reject(assembled, mutate, r"Axiom 37 \(BackupRelays\)")

def running_channel(d: dict, name: str) -> dict:
    return next(c for c in d["DerivedChannels"] if c["Name"] == name)


def test_gw_house0_no_sieg_axiom_38_a_running_channel_missing(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DerivedChannels"].remove(running_channel(d, "secondary-pump-running"))

    reject(assembled, mutate, r"Axiom 38 \(CirculatorRunningChannels\) a\.")


def test_gw_house0_no_sieg_axiom_38_a_wrong_strategy(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        running_channel(d, "secondary-pump-running")["Strategy"] = "sum"

    reject(assembled, mutate, r"Axiom 38 \(CirculatorRunningChannels\) a\.")


def test_gw_house0_no_sieg_axiom_38_b_input_is_the_declared_power_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        running_channel(d, "secondary-pump-running")["InputChannelNames"] = ["hp-odu-pwr"]

    reject(assembled, mutate, r"Axiom 38 \(CirculatorRunningChannels\) b\.")


def test_gw_house0_no_sieg_axiom_38_b_declared_input_is_not_a_derived_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circ = next(c for c in d["Hydronic"]["Circulators"] if c["PumpNodeName"] == "secondary-pump")
        circ["PowerChannelName"] = "store-pump-running"
        running_channel(d, "secondary-pump-running")["InputChannelNames"] = ["store-pump-running"]

    reject(assembled, mutate, r"Axiom 38 \(CirculatorRunningChannels\) b\.")


def test_gw_house0_no_sieg_axiom_38_b_ct_input_when_no_power_channel(assembled: dict) -> None:
    """A circulator with only a CT reads the CT; reading the power channel fails."""

    def mutate(d: dict) -> None:
        circ = next(c for c in d["Hydronic"]["Circulators"] if c["PumpNodeName"] == "secondary-pump")
        del circ["PowerChannelName"]
        circ["CtChannelName"] = "secondary-pump-ct"
        d["DataChannels"].append(
            {
                **next(c for c in d["DataChannels"] if c["Name"] == "secondary-pump-pwr"),
                "Name": "secondary-pump-ct",
                "TelemetryName": "VoltsTimes100",
                "Quantity": "Voltage",
                "Id": "7d2e6c1a-5b3f-4a8e-9c0d-1e2f3a4b5c6d",
            }
        )

    reject(assembled, mutate, r"Axiom 38 \(CirculatorRunningChannels\) b\.")


def test_gw_house0_no_sieg_axiom_39_hp_watch_absent(assembled: dict) -> None:
    reject(
        assembled,
        lambda d: d.update(ShNodes=[n for n in d["ShNodes"] if n["Name"] != "hp-watch"]),
        "Axiom 39",
    )


def test_gw_house0_no_sieg_axiom_39_hp_watch_wrong_actor_class(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-watch":
                n["ActorClass"] = "NoActor"
                del n["ActorHierarchyName"]

    reject(assembled, mutate, "Axiom 39")

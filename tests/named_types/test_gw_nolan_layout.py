"""Rejecting tests for gw.nolan.layout/000's nine axioms.

Each counterexample is a typed mutation of the assembled fixture pair,
re-validated at the boundary — chosen so the intended axiom fires (not an
earlier one; e.g. dropping a transactive-metered node would trip axiom 1
before axiom 5 saw it)."""

import json
import uuid
from pathlib import Path

import pytest

from gwsproto.named_types import NolanLayout, OperationalParams
from sema_to_dc import assemble_runtime_layout

CONFIG = Path(__file__).parent.parent / "config"


@pytest.fixture(scope="module")
def assembled() -> dict:
    ops = OperationalParams.model_validate_json(
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


def set_handle(name: str, handle: str):
    def mutate(d: dict) -> None:
        next(n for n in d["ShNodes"] if n["Name"] == name)["Handle"] = handle
    return mutate


def test_gw_nolan_layout_axiom_30_command_node_declared_under_lc(assembled: dict) -> None:
    """hp-boss and its relay move together so the tree stays prefix-closed
    and the handle axiom is the one that rejects."""
    def mutate(d: dict) -> None:
        set_handle("hp-boss", "auto.lc.n.hp-boss")(d)
        set_handle("hp-scada-ops-relay", "auto.lc.n.hp-boss.hp-scada-ops-relay")(d)
    reject(assembled, mutate, "Axiom 30")


def test_gw_nolan_layout_axiom_30_fixed_relay_declared_flat(assembled: dict) -> None:
    reject(assembled, set_handle("hp-scada-ops-relay", "auto.hp-scada-ops-relay"), "Axiom 30")


def test_gw_nolan_layout_axiom_30_floating_actuator_under_a_boss(assembled: dict) -> None:
    reject(assembled, set_handle("store-pump-relay", "auto.lc.n.store-pump-relay"), "Axiom 30")


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


def test_gw_nolan_layout_axiom_5_output_actor_class(assembled: dict) -> None:
    """The 0-10V output is an actuator leaf: a secondary-010v node that is
    not a ZeroTenOutputer is rejected."""
    def reclass(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "secondary-010v":
                n["ActorClass"] = "Relay"
    reject(assembled, reclass, "Axiom 5")


def test_gw_nolan_layout_axiom_5_output_component(assembled: dict) -> None:
    """secondary-010v must hold an i2c.dac.output.component.gt: pointing it
    at the web server's component is rejected."""
    def rebind(d: dict) -> None:
        web = next(n for n in d["ShNodes"] if n["Name"] == "web-server")
        for n in d["ShNodes"]:
            if n["Name"] == "secondary-010v":
                n["ComponentId"] = web["ComponentId"]
    reject(assembled, rebind, "Axiom 5")


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


def test_gw_hydronic_axiom_1_a_store_tanks(assembled: dict) -> None:
    """Zero store tanks is a layout whose store is not water tanks; seven is
    past the bound."""
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    h["TotalStoreTanks"] = 0
    assert Hydronic.model_validate(h).TotalStoreTanks == 0
    h["TotalStoreTanks"] = 7
    with pytest.raises(ValueError, match="Axiom 1"):
        Hydronic.model_validate(h)


def test_gw_hydronic_axiom_1_b_no_zones(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    h["Zones"] = []
    h["ZoneCallCircuits"] = []
    with pytest.raises(ValueError, match="Axiom 1"):
        Hydronic.model_validate(h)


def test_gw_hydronic_zone_call_circuits_required(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    del h["ZoneCallCircuits"]
    with pytest.raises(ValueError, match="ZoneCallCircuits"):
        Hydronic.model_validate(h)


def test_gw_hydronic_axiom_2(assembled: dict) -> None:
    from gwsproto.named_types import Hydronic

    h = json.loads(json.dumps(assembled["Hydronic"]))
    h["ZoneCallCircuits"][0]["ServesZone"] = "no-such-zone"
    with pytest.raises(ValueError, match="Axiom 2"):
        Hydronic.model_validate(h)


def declare_twin(d: dict, handle: str | None = "auto.hp-boss.hp-ctrl-box") -> None:
    d["Hydronic"]["HpCommandNodeName"] = "hp-ctrl-box"
    for n in d["ShNodes"]:
        if n["Name"] == "hp-ctrl-box":
            n["ActorClass"] = "HpTwin"
            n["ActorHierarchyName"] = "s.hp-ctrl-box"
            if handle is not None:
                n["Handle"] = handle


def test_gw_nolan_layout_axiom_10_declared_twin_accepted(assembled: dict) -> None:
    """spruce with the MIM wired: hp-ctrl-box as HpTwin under hp-boss."""
    NolanLayout.model_validate(mutated(assembled, declare_twin))


def test_gw_nolan_layout_axiom_10_a_no_actor(assembled: dict) -> None:
    def declare_only(d: dict) -> None:
        d["Hydronic"]["HpCommandNodeName"] = "hp-ctrl-box"
    reject(assembled, declare_only, "Axiom 10")


def test_gw_nolan_layout_axiom_10_a_wrong_parent(assembled: dict) -> None:
    reject(assembled, lambda d: declare_twin(d, handle="auto.lc.n.hp-ctrl-box"), "Axiom 10")


def test_gw_nolan_layout_axiom_10_b_undeclared_twin(assembled: dict) -> None:
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
    reject(assembled, stray_twin, "Axiom 10")


def test_gw_nolan_layout_axiom_11(assembled: dict) -> None:
    """A relay handle whose parent names no ShNode is an orphan."""
    def orphan(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n["Handle"] = "auto.nobody.vdc-relay"
    reject(assembled, orphan, "Axiom 11")


def test_gw_nolan_layout_axiom_12_a(assembled: dict) -> None:
    """An actuator with a bare Name for a handle has no boss."""
    def undotted(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "vdc-relay":
                n.pop("Handle", None)
    reject(assembled, undotted, "Axiom 12")


def test_gw_nolan_layout_axiom_12_b(assembled: dict) -> None:
    """hp-odu (NoActor) given a handle under hp-boss is a leaf that is
    neither actuator nor command node."""
    def stray_leaf(d: dict) -> None:
        for n in d["ShNodes"]:
            if n["Name"] == "hp-odu":
                n["Handle"] = "auto.hp-boss.hp-odu"
    reject(assembled, stray_leaf, "Axiom 12")


def test_gw_nolan_layout_axiom_13_unknown_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        d["Hydronic"]["Zones"][0]["TempChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 13")


def test_gw_nolan_layout_axiom_13_not_a_temperature(assembled: dict) -> None:
    def point_at_flow(d: dict) -> None:
        d["Hydronic"]["Zones"][0]["TempChannelName"] = "primary-flow"

    reject(assembled, point_at_flow, "Axiom 13")


def test_gw_nolan_layout_axiom_14_unknown_whitewire_channel(assembled: dict) -> None:
    def rename(d: dict) -> None:
        circuit = d["Hydronic"]["ZoneCallCircuits"][0]
        for c in d["DerivedChannels"]:
            if c["InputChannelNames"] == [circuit["WhitewireChannelName"]]:
                c["InputChannelNames"] = ["no-such-channel"]
        circuit["WhitewireChannelName"] = "no-such-channel"

    reject(assembled, rename, "Axiom 14")


def test_gw_nolan_layout_axiom_15_missing_heat_call(assembled: dict) -> None:
    def drop(d: dict) -> None:
        whitewire = d["Hydronic"]["ZoneCallCircuits"][0]["WhitewireChannelName"]
        d["DerivedChannels"] = [
            c
            for c in d["DerivedChannels"]
            if not (c["Strategy"] == "heat-call" and c["InputChannelNames"] == [whitewire])
        ]

    reject(assembled, drop, "Axiom 15")


def test_gw_nolan_layout_axiom_15_second_heat_call(assembled: dict) -> None:
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

    reject(assembled, duplicate, "Axiom 15")


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


def test_gw_nolan_layout_axiom_16_a_creator_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 16 \(.*failed \(a\)")


def test_gw_nolan_layout_axiom_16_b_creator_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["CreatedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 16 \(.*failed \(b\)")


def test_gw_nolan_layout_axiom_17_a_about_node_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["AboutNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 17 \(.*failed \(a\)")


def test_gw_nolan_layout_axiom_17_b_capturer_is_a_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = "no-such-node"

    reject(assembled, mutate, r"Axiom 17 \(.*failed \(b\)")


def test_gw_nolan_layout_axiom_17_c_capturer_has_an_actor(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"][-1]["CapturedByNodeName"] = no_actor_node_name(d)

    reject(assembled, mutate, r"Axiom 17 \(.*failed \(c\)")


def test_gw_nolan_layout_axiom_18_a_input_is_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        free_derived(d)[-1]["InputChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 18 \(.*failed \(a\)")


def test_gw_nolan_layout_axiom_18_b_self_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        channel = free_derived(d)[-1]
        channel["InputChannelNames"] = [channel["Name"]]

    reject(assembled, mutate, r"Axiom 18 \(.*failed \(b\)")


def test_gw_nolan_layout_axiom_18_b_two_channel_cycle(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]
        second["InputChannelNames"] = [first["Name"]]

    reject(assembled, mutate, r"Axiom 18 \(.*failed \(b\)")


def test_gw_nolan_layout_axiom_18_derived_input_chain_accepted(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first, second = free_derived(d)[-2:]
        first["InputChannelNames"] = [second["Name"]]

    NolanLayout.model_validate(mutated(assembled, mutate))


def test_gw_nolan_layout_axiom_19_derived_shares_a_data_channel_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, d["DataChannels"][-1]["Name"])

    reject(assembled, mutate, r"Axiom 19 \(")


def test_gw_nolan_layout_axiom_19_two_derived_share_a_name(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        add_derived_copy(d, free_derived(d)[-1]["Name"])

    reject(assembled, mutate, r"Axiom 19 \(")


def drop_channel(d: dict, name: str) -> None:
    d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != name]
    d["DerivedChannels"] = [c for c in d["DerivedChannels"] if c["Name"] != name]


def first_circuit(d: dict) -> dict:
    return d["Hydronic"]["ZoneCallCircuits"][0]


def test_gw_nolan_layout_axiom_20_missing_buffer_depth(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_channel(d, "buffer-depth1")

    reject(assembled, mutate, r"Axiom 20 \(")


def test_gw_nolan_layout_axiom_21_missing_tank_depth(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_channel(d, "tank1-depth1")

    reject(assembled, mutate, r"Axiom 21 \(")


def test_gw_nolan_layout_axiom_22_missing_usable_energy(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        drop_channel(d, "usable-energy")

    reject(assembled, mutate, r"Axiom 22 \(")


def test_gw_nolan_layout_axiom_23_web_server_node_absent(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        for node in d["ShNodes"]:
            if node["Name"] == "web-server":
                node["Name"] = "web-server2"

    reject(assembled, mutate, r"Axiom 23 \(")


def test_gw_nolan_layout_axiom_24_a_slab_circuit_without_a_floor_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit.pop("FloorTempChannelName", None)

    reject(assembled, mutate, r"Axiom 24 \(")


def test_gw_nolan_layout_axiom_24_b_floor_channel_does_not_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "no-such-channel"

    reject(assembled, mutate, r"Axiom 24 \(")


def test_gw_nolan_layout_axiom_24_b_floor_channel_is_not_a_temperature(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        first_circuit(d)["FloorTempChannelName"] = "dist-flow"

    reject(assembled, mutate, r"Axiom 24 \(")


def test_gw_nolan_layout_axiom_24_slab_circuit_with_a_temperature_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        circuit = first_circuit(d)
        circuit["EmitterType"] = "RadiantSlab"
        circuit["CanCool"] = False
        circuit["FloorTempChannelName"] = "dist-swt"

    NolanLayout.model_validate(mutated(assembled, mutate))


def test_gw_nolan_layout_axiom_25_disabled_node_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = ["no-such-node"]

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_nolan_layout_axiom_25_disabled_channel_must_resolve(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledChannelNames"] = ["no-such-channel"]

    reject(assembled, mutate, r"Axiom 25 \(")


def test_gw_nolan_layout_axiom_26_disabled_node_captures_nothing(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [no_actor_node_name(d)]

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_nolan_layout_axiom_26_captured_channel_not_listed(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DisabledNodeNames"] = [d["DataChannels"][0]["CapturedByNodeName"]]
        d["DisabledChannelNames"] = []

    reject(assembled, mutate, r"Axiom 26 \(")


def test_gw_nolan_layout_axiom_26_disabled_node_with_its_channels(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        node = d["DataChannels"][0]["CapturedByNodeName"]
        captured = [c["Name"] for c in d["DataChannels"] if c["CapturedByNodeName"] == node]
        derived = [c["Name"] for c in d["DerivedChannels"] if set(c["InputChannelNames"]) & set(captured)]
        d["DisabledNodeNames"] = [node]
        d["DisabledChannelNames"] = captured + derived

    NolanLayout.model_validate(mutated(assembled, mutate))


def test_gw_nolan_layout_axiom_27_enabled_derived_reads_disabled_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        derived = next(c for c in d["DerivedChannels"] if c["InputChannelNames"])
        d["DisabledChannelNames"] = [derived["InputChannelNames"][0]]

    reject(assembled, mutate, r"Axiom 27 \(")


def test_gw_nolan_layout_axiom_27_disabled_derived_may_read_disabled_input(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        derived = next(c for c in d["DerivedChannels"] if c["InputChannelNames"])
        d["DisabledChannelNames"] = [derived["InputChannelNames"][0], derived["Name"]]

    NolanLayout.model_validate(mutated(assembled, mutate))

def test_gw_nolan_layout_axiom_28_a_actuator_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != "vdc-relay"]

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_nolan_layout_axiom_28_a_actuator_channel_about_another_node(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        next(c for c in d["DataChannels"] if c["Name"] == "vdc-relay")["AboutNodeName"] = "hp-scada-ops-relay"

    reject(assembled, mutate, r"Axiom 28 \(")


def test_gw_nolan_layout_axiom_28_a_circuit_relay_without_a_channel(assembled: dict) -> None:
    def mutate(d: dict) -> None:
        relay = d["Hydronic"]["ZoneCallCircuits"][0]["OpsRelayNode"]
        d["DataChannels"] = [c for c in d["DataChannels"] if c["Name"] != relay]

    reject(assembled, mutate, r"Axiom 28 \(")


@pytest.mark.parametrize(
    ("name", "telemetry", "quantity"),
    [("vdc-relay", "VoltsTimesTen", "Voltage"), ("secondary-010v", "RelayState", "Unitless")],
)
def test_gw_nolan_layout_axiom_28_b_actuator_channel_telemetry(
    assembled: dict, name: str, telemetry: str, quantity: str
) -> None:
    """The quantity moves with the telemetry so data.channel.gt's own
    consistency check is not what fires."""

    def mutate(d: dict) -> None:
        channel = next(c for c in d["DataChannels"] if c["Name"] == name)
        channel["TelemetryName"] = telemetry
        channel["Quantity"] = quantity

    reject(assembled, mutate, r"Axiom 28 \(")



def control_box_record(d: dict, factory_installed: bool, overridable: bool) -> dict:
    box = next(n for n in d["ShNodes"] if n["Name"] == "hp-ctrl-box")
    device_type = next(
        c for c in d["Components"] if c["ComponentId"] == box["ComponentId"]
    )["DeviceType"]
    return {
        "TypeName": "hp.control.box.device.type.gt",
        "Version": "000",
        "DeviceType": device_type,
        "PrimaryPumpFactoryInstalled": factory_installed,
        "PrimaryPumpOverridable": overridable,
        "PrimaryPumpAlwaysOn": False,
    }


def test_gw_nolan_layout_axiom_29_scada_owner_against_a_non_overridable_factory_pump(
    assembled: dict,
) -> None:
    def mutate(d: dict) -> None:
        d["Hydronic"]["PrimaryPumpOwner"] = "Scada"
        d["DeviceTypes"].append(control_box_record(d, True, False))

    reject(assembled, mutate, r"Axiom 29 \(")


def test_gw_nolan_layout_axiom_29_scada_owner_against_an_overridable_control_box_is_accepted(
    assembled: dict,
) -> None:
    def mutate(d: dict) -> None:
        d["Hydronic"]["PrimaryPumpOwner"] = "Scada"
        d["DeviceTypes"].append(control_box_record(d, True, True))

    NolanLayout.model_validate(mutated(assembled, mutate))

from gwsproto.named_types import LayoutLite
from tests.named_types.sema_oracle import assert_refused


def layout_lite_dict() -> dict:
    return {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.beech.scada",
        "CreatedMs": 1728651445746,
        "MessageId": "1302c0f8-1983-43b2-90d2-61678d731db3",
        "HardwareLayoutTypeName": "gw.house0.layout",
        "ZoneList": ["Down", "Up"],
        "CriticalZoneList": ["Down"],
        "ShNodes": [
            {
                "ActorClass": "PrimaryScada",
                "DisplayName": "Keene Beech Scada",
                "Name": "s",
                "ShNodeId": "da9a0427-d6c0-44c0-b51c-492c1e580dc5",
                "TypeName": "spaceheat.node.gt",
                "Version": "303",
            },
            {
                "ActorClass": "PowerMeter",
                "ActorHierarchyName": "s.power-meter",
                "ComponentId": "9633adef-2373-422d-8a0e-dfbd16ae081c",
                "DisplayName": "Primary Power Meter",
                "Name": "power-meter",
                "ShNodeId": "6c0563b7-5171-4b1c-bba3-de156bea4b95",
                "TypeName": "spaceheat.node.gt",
                "Version": "303",
            },
            {
                "ActorClass": "NoActor",
                "DisplayName": "Hp Idu",
                "Name": "hp-idu",
                "NameplatePowerW": 4000,
                "ShNodeId": "07b8ca98-12c4-4510-8d0f-14fda2331215",
                "TypeName": "spaceheat.node.gt",
                "Version": "303",
            },
        ],
        "DerivedChannels": [
        ],
        "StateMachines": [
            {
                "NodeName": "s",
                "StateEnum": "gw.top.state",
                "StateEnumVersion": "000",
                "TypeName": "gw.state.machine",
                "Version": "000",
            }
        ],
        "DataChannels": [
            {
                "Name": "hp-idu-pwr",
                "DisplayName": "Hp IDU",
                "AboutNodeName": "hp-idu",
                "CapturedByNodeName": "power-meter",
                "TelemetryName": "PowerW",
                "Quantity": "Power",
                "TerminalAssetAlias": "hw1.isone.me.versant.keene.beech.ta",
                "StartS": 1721405699,
                "Id": "50cf426b-ff3f-4a30-8415-8d3fba5e0ab7",
                "TypeName": "data.channel.gt",
                "Version": "004",
            }
        ],
            "TypeName": "layout.lite",
            "Version": "013",
        }



def test_layout_lite_generated() -> None:
    d = layout_lite_dict()
    d2 = LayoutLite.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def machine(node_name: str) -> dict:
    return {
        "NodeName": node_name,
        "StateEnum": "gw.top.state",
        "StateEnumVersion": "000",
        "TypeName": "gw.state.machine",
        "Version": "000",
    }


def test_layout_lite_axiom_5_unknown_node() -> None:
    d = layout_lite_dict()
    d["StateMachines"] = [machine("hp-boss")]
    assert_refused(LayoutLite, d, match="Axiom 5")


def test_layout_lite_axiom_5_two_machines_on_one_node() -> None:
    d = layout_lite_dict()
    d["StateMachines"] = [machine("s"), machine("s")]
    assert_refused(LayoutLite, d, match="Axiom 5")

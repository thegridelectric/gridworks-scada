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
        "Tariff": {
            "TypeName": "gw.tou.tariff",
            "Version": "000",
            "Alias": "versant.a1.home.eco.bonus",
            "DisplayName": "Home Eco Rate with Bonus Meter",
            "TimezoneStr": "America/New_York",
            "OnPeakWindows": [
                {
                    "TypeName": "gw.tou.window",
                    "Version": "000",
                    "Start": "07:00",
                    "End": "12:00",
                    "Days": [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday"
                    ]
                },
                {
                    "TypeName": "gw.tou.window",
                    "Version": "000",
                    "Start": "16:00",
                    "End": "20:00",
                    "Days": [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday"
                    ]
                }
            ]
        },
        "TypeName": "layout.lite",
        "Version": "014",
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


def test_layout_lite_axiom_1_about_node_unknown() -> None:
    d = layout_lite_dict()
    d["DataChannels"][0]["AboutNodeName"] = "buffer"
    assert_refused(LayoutLite, d, match="Axiom 1")


def test_layout_lite_axiom_2_boss_missing() -> None:
    d = layout_lite_dict()
    d["ShNodes"][2]["Handle"] = "auto.hp-boss.hp-idu"
    assert_refused(LayoutLite, d, match="Axiom 2")


def test_layout_lite_axiom_3_critical_zone_not_a_zone() -> None:
    d = layout_lite_dict()
    d["CriticalZoneList"] = ["Attic"]
    assert_refused(LayoutLite, d, match="Axiom 3")


def test_layout_lite_axiom_4_created_by_node_unknown() -> None:
    d = layout_lite_dict()
    d["DerivedChannels"] = [
        {
            "Id": "9b1f1a3e-6c0e-4d9a-9f4e-2a1b3c4d5e6f",
            "Name": "hp-idu-pwr-avg",
            "CreatedByNodeName": "derived-maker",
            "Strategy": "average",
            "InputChannelNames": ["hp-idu-pwr"],
            "OutputUnit": "Watts",
            "OutputQuantity": "Power",
            "EmissionMethod": "Periodic",
            "EmitPeriodS": 60,
            "DisplayName": "Hp IDU power, averaged",
            "TerminalAssetAlias": "hw1.isone.me.versant.keene.beech.ta",
            "TypeName": "derived.channel.gt",
            "Version": "003",
        }
    ]
    assert_refused(LayoutLite, d, match="Axiom 4")

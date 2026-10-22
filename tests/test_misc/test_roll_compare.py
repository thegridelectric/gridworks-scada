"""scripts/roll_compare.py: the match rules the roll script applies."""

import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "roll_compare", Path(__file__).parents[2] / "scripts" / "roll_compare.py"
)
roll_compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(roll_compare)

OPS = {
    "ScadaAlias": "hw1.isone.me.versant.keene.spruce.scada",
    "DispatchHold": {"OperatorHold": False, "ServiceContractBroken": False},
    "HeatingCurve": {"AlphaTimes10": 120, "BetaTimes100": -20},
    "TypeName": "gw.operational.params",
}


def test_layout_matches_only_byte_for_byte():
    a = json.dumps({"ShNodes": [], "Strategy": "House0"}).encode()
    b = json.dumps({"Strategy": "House0", "ShNodes": []}).encode()
    assert roll_compare.layout_matches(a, a)
    assert not roll_compare.layout_matches(a, b)


def test_ops_dispatch_hold_is_the_scada_s_to_write():
    latched = json.loads(json.dumps(OPS))
    latched["DispatchHold"]["ServiceContractBroken"] = True
    assert roll_compare.ops_differences(OPS, latched) == []


def test_ops_any_other_difference_is_reported_by_path():
    changed = json.loads(json.dumps(OPS))
    changed["HeatingCurve"]["AlphaTimes10"] = 130
    changed["DispatchHold"]["OperatorHold"] = True
    assert roll_compare.ops_differences(OPS, changed) == ["HeatingCurve.AlphaTimes10"]


def test_ops_missing_and_extra_fields_are_differences():
    extra = json.loads(json.dumps(OPS))
    extra["HorizonHours"] = 48
    del extra["HeatingCurve"]["BetaTimes100"]
    assert roll_compare.ops_differences(OPS, extra) == [
        "HeatingCurve.BetaTimes100",
        "HorizonHours",
    ]


def layout_with_s2() -> dict:
    """A House0-shaped layout cut down to one node per scada: the power
    meter under s2, a relay under s, and one channel captured by each."""
    return {
        "ShNodes": [
            {"Name": "s", "ActorClass": "Scada"},
            {"Name": "s2", "ActorClass": "Parentless"},
            {"Name": "power-meter", "ActorHierarchyName": "s2.power-meter", "ComponentId": "meter-c"},
            {"Name": "relay1", "ActorHierarchyName": "s.relay1", "ComponentId": "relay-c"},
            {"Name": "hp-odu", "ActorHierarchyName": "s.hp-odu"},
        ],
        "ElectricMeterComponents": [
            {"ComponentId": "meter-c", "ComponentAttributeClassId": "meter-cac",
             "ConfigList": [{"ChannelName": "hp-odu-pwr", "AsyncCaptureDelta": 2}]},
        ],
        "OtherComponents": [
            {"ComponentId": "relay-c", "ComponentAttributeClassId": "relay-cac"},
        ],
        "ElectricMeterCacs": [{"ComponentAttributeClassId": "meter-cac", "MakeModel": "EGAUGE__4030"}],
        "OtherCacs": [{"ComponentAttributeClassId": "relay-cac", "MakeModel": "KRIDA__DOUBLEEMR16I2CV3"}],
        "DataChannels": [
            {"Name": "hp-odu-pwr", "AboutNodeName": "hp-odu", "CapturedByNodeName": "power-meter"},
            {"Name": "relay1", "AboutNodeName": "relay1", "CapturedByNodeName": "s"},
        ],
        "UseSiegLoop": False,
    }


def test_sensed_part_is_the_s2_hierarchy_and_what_it_captures():
    part = roll_compare.sensed_part(layout_with_s2())
    assert sorted(part["ShNodes"]) == ["power-meter", "s2"]
    assert list(part["Components"]) == ["meter-c"]
    assert list(part["Cacs"]) == ["meter-cac"]
    assert list(part["DataChannels"]) == ["hp-odu-pwr"]


def test_sensed_ignores_the_primary_scada_s_part():
    box = layout_with_s2()
    box["ShNodes"][3]["ComponentId"] = "relay-c2"
    box["OtherComponents"][0]["ComponentId"] = "relay-c2"
    box["DataChannels"][1]["Name"] = "relay1-state"
    box["UseSiegLoop"] = True
    del box["ShNodes"][4]
    assert roll_compare.sensed_differences(layout_with_s2(), box) == []


def test_sensed_reports_a_change_in_what_s2_senses():
    box = layout_with_s2()
    box["ElectricMeterComponents"][0]["ConfigList"][0]["AsyncCaptureDelta"] = 1
    box["DataChannels"].append(
        {"Name": "dist-pump-pwr", "AboutNodeName": "dist-pump", "CapturedByNodeName": "power-meter"}
    )
    assert roll_compare.sensed_differences(layout_with_s2(), box) == [
        "Components.meter-c.ConfigList",
        "DataChannels.dist-pump-pwr.AboutNodeName",
        "DataChannels.dist-pump-pwr.CapturedByNodeName",
        "DataChannels.dist-pump-pwr.Name",
    ]

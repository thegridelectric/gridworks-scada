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


"""Tests glitch type, version 000"""
import json
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch


def test_glitch_generated() -> None:
    d = {
        "FromGNodeAlias": "hw1.isone.me.versant.keene.beech.scada",
        "Node": "power-meter",
        "Type": "Warning",
        "Summary":  "Driver problems: read warnings for (EGAUGE__4030)",
        "Details": "Problems: 0 errors, 2 warnings, max: 10",
        "CreatedMs": 1736825676763,
        "TypeName": "glitch",
        "Version": "000",
    }
    t = Glitch.model_validate(d).model_dump_json(exclude_none=True)
    d2 =json.loads(t)
    assert d2 == d

    assert d2 == d

    ######################################
    # Enum related
    ######################################

    assert type(d2["Type"]) is str

    d2 = dict(d, Type="unknown_enum_thing")
    assert Glitch(**d2).Type == LogLevel.default()

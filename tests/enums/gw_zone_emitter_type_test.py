"""
Tests for enum gw.zone.emitter.type.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import GwZoneEmitterType


def test_gw_zone_emitter_type() -> None:
    assert set(GwZoneEmitterType.values()) == {
        "Other",
        "RadiantSlab",
        "FanCoil",
    }

    assert GwZoneEmitterType.default() == GwZoneEmitterType.Other
    assert GwZoneEmitterType.enum_name() == "gw.zone.emitter.type"
    assert GwZoneEmitterType.enum_version() == "000"

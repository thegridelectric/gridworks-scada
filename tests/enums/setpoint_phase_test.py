"""
Tests for enum setpoint.phase.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import SetpointPhase


def test_setpoint_phase() -> None:
    assert set(SetpointPhase.values()) == {
        "Unknown",
        "LastHeatCallEndTemp",
        "SuspectZoneBelowSetpoint",
        "SuspectZoneAboveSetpoint",
    }

    assert SetpointPhase.default() == SetpointPhase.Unknown
    assert SetpointPhase.enum_name() == "setpoint.phase"
    assert SetpointPhase.enum_version() == "000"

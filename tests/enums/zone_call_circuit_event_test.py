"""
Tests for enum zone.call.circuit.event.000 from the GridWorks Type Registry.
"""

from gwsproto.enums import ZoneCallCircuitEvent


def test_zone_call_circuit_event() -> None:
    assert set(ZoneCallCircuitEvent.values()) == {
        "WakeUp",
        "GoDormant",
        "Release",
        "ScadaHold",
        "ScadaCall",
        "ConfirmHeld",
        "ConfirmCalling",
        "ConfirmReleased",
        "ActuationFailed",
    }

    assert ZoneCallCircuitEvent.default() == ZoneCallCircuitEvent.GoDormant
    assert ZoneCallCircuitEvent.enum_name() == "zone.call.circuit.event"
    assert ZoneCallCircuitEvent.enum_version() == "000"

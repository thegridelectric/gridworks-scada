"""Tests gw1.zone.call.circuit type, version 000"""

import pytest

from gwsproto.named_types import ZoneCallCircuit


def base_circuit() -> dict:
    return {
        "CircuitPosition": 1,
        "ServesZone": "zone1-down",
        "ActuatorKind": "FloorLoop",
        "Role": "Baseload",
        "CanCool": False,
        "SetpointSource": "Learned",
        "Thermostat": {
            "Kind": "MechanicalDial",
            "TypeName": "gw1.zone.thermostat",
            "Version": "000",
        },
        "WhitewireChannelName": "zone1-down-whitewire",
        "FailsafeRelayNode": "relay6",
        "OpsRelayNode": "relay7",
        "TypeName": "gw1.zone.call.circuit",
        "Version": "000",
    }


def test_zone_call_circuit_generated() -> None:
    d = base_circuit()

    d2 = ZoneCallCircuit.model_validate(d).model_dump(by_alias=True, exclude_none=True)

    assert d2 == d


def test_zone_call_circuit_axiom_1() -> None:
    d = base_circuit()
    d["CanCool"] = True

    with pytest.raises(ValueError, match="Axiom 1 \\(FloorLoopsCannotCool\\) failed"):
        ZoneCallCircuit.model_validate(d)


def test_zone_call_circuit_axiom_2() -> None:
    d = base_circuit()
    d["SetpointSource"] = "FromThermostat"

    with pytest.raises(
        ValueError, match="Axiom 2 \\(ReadSetpointNeedsCommsStat\\) failed"
    ):
        ZoneCallCircuit.model_validate(d)

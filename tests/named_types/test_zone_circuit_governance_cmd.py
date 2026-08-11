"""Tests zone.circuit.governance.cmd type, version 000"""

import pytest

from gwsproto.named_types import ZoneCircuitGovernanceCmd


def base_cmd() -> dict:
    return {
        "FromHandle": "auto",
        "ToHandle": "auto.zone1-down-circuit",
        "Event": "SwitchToThermostatic",
        "SetpointF": 68.5,
        "TriggerId": "3d2f3d92-2f8a-4f9e-8b6d-6f9df9c2b0aa",
        "SendTimeUnixMs": 1754900000000,
        "TypeName": "zone.circuit.governance.cmd",
        "Version": "000",
    }


def test_zone_circuit_governance_cmd_generated() -> None:
    d = base_cmd()

    d2 = ZoneCircuitGovernanceCmd.model_validate(d).model_dump(
        by_alias=True, exclude_none=True
    )

    assert d2 == d


def test_zone_circuit_governance_cmd_axiom_1_a() -> None:
    d = base_cmd()
    del d["SetpointF"]

    with pytest.raises(
        ValueError, match="Axiom 1 \\(SetpointIffThermostatic\\) failed"
    ):
        ZoneCircuitGovernanceCmd.model_validate(d)


def test_zone_circuit_governance_cmd_axiom_1_b() -> None:
    d = base_cmd()
    d["Event"] = "SwitchToOff"

    with pytest.raises(
        ValueError, match="Axiom 1 \\(SetpointIffThermostatic\\) failed"
    ):
        ZoneCircuitGovernanceCmd.model_validate(d)

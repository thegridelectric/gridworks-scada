"""Tests setpoint.belief type, version 000"""

import pytest

from gwsproto.named_types import SetpointBelief


def base_belief() -> dict:
    return {
        "Phase": "LastHeatCallEndTemp",
        "ValueF": 67.0,
        "TypeName": "setpoint.belief",
        "Version": "000",
    }


def test_setpoint_belief_generated() -> None:
    d = base_belief()

    d2 = SetpointBelief.model_validate(d).model_dump(by_alias=True, exclude_none=True)

    assert d2 == d


def test_setpoint_belief_axiom_1_a() -> None:
    d = base_belief()
    d["Phase"] = "Unknown"

    with pytest.raises(ValueError, match="Axiom 1 \\(UnknownIsValueless\\) failed"):
        SetpointBelief.model_validate(d)


def test_setpoint_belief_axiom_1_b() -> None:
    d = base_belief()
    del d["ValueF"]

    with pytest.raises(ValueError, match="Axiom 1 \\(UnknownIsValueless\\) failed"):
        SetpointBelief.model_validate(d)

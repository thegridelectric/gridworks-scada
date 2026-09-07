"""Tests analog.dispatch type, version 000"""

import pytest
from gwsproto.named_types import AnalogDispatch
from pydantic import ValidationError


def test_analog_dispatch_generated() -> None:
    d = {
        "FromHandle": "admin",
        "ToHandle": "admin.primary-010v",
        "AboutName": "primary-010v",
        "Value": 65,
        "TriggerId": "1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
        "UnixTimeMs": 1757282100000,
        "TypeName": "analog.dispatch",
        "Version": "000",
    }

    d2 = AnalogDispatch.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_analog_dispatch_axiom_1() -> None:
    """FromHandle must be the immediate boss of ToHandle."""
    with pytest.raises(ValidationError, match="Axiom 1"):
        AnalogDispatch(
            FromHandle="auto",
            ToHandle="admin.primary-010v",
            AboutName="primary-010v",
            Value=65,
            TriggerId="1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
            UnixTimeMs=1757282100000,
        )


def test_analog_dispatch_axiom_1_multiplexer_exempt() -> None:
    AnalogDispatch(
        FromHandle="admin.primary-010v",
        ToHandle="admin.dfr-multiplexer",
        AboutName="primary-010v",
        Value=65,
        TriggerId="1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
        UnixTimeMs=1757282100000,
    )

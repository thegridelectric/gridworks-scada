"""Tests gw.dispatch.nack type, version 000"""

from gwsproto.enums import GwScadaCmdRefusalReason
from gwsproto.named_types import DispatchNack


def test_dispatch_nack_generated() -> None:
    d = {
        "FromHandle": "admin.pico-cycler",
        "ToHandle": "admin",
        "TriggerId": "1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
        "Reason": "Busy",
        "UnixTimeMs": 1757282100250,
        "TypeName": "gw.dispatch.nack",
        "Version": "000",
    }

    d2 = DispatchNack.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
    assert DispatchNack.model_validate(d).Reason == GwScadaCmdRefusalReason.Busy


def test_dispatch_nack_unknown_reason_coerces_to_default() -> None:
    d = {
        "FromHandle": "admin.pico-cycler",
        "ToHandle": "admin",
        "TriggerId": "1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
        "Reason": "Garbage",
        "UnixTimeMs": 1757282100250,
        "TypeName": "gw.dispatch.nack",
        "Version": "000",
    }
    assert DispatchNack.model_validate(d).Reason == GwScadaCmdRefusalReason.Unknown


"""Tests gw.dispatch.ack type, version 000"""

import pytest
from gwsproto.named_types import DispatchAck
from pydantic import ValidationError


def test_gw_dispatch_ack_axiom_1() -> None:
    """ToHandle must be the immediate boss of FromHandle."""
    with pytest.raises(ValidationError, match="Axiom 1"):
        DispatchAck(
            FromHandle="admin.pico-cycler",
            ToHandle="auto",
            TriggerId="1c0d8f5e-3f4a-4b3c-9d2e-7a6b5c4d3e2f",
            UnixTimeMs=1757282100250,
        )

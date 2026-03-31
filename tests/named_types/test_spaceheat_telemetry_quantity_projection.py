"""Tests spaceheat.telemetry.quantity.projection type, version 000"""

import pytest

from gwsproto.named_types import SpaceheatTelemetryQuantityProjection


def test_spaceheat_telemetry_quantity_projection_generated() -> None:
    d = {
        "TelemetryName": "PowerW",
        "Quantity": "Power",
        "TypeName": "spaceheat.telemetry.quantity.projection",
        "Version": "000",
    }

    d2 = SpaceheatTelemetryQuantityProjection.model_validate(d).model_dump(
        exclude_none=True
    )

    assert d2 == d


def test_spaceheat_telemetry_quantity_projection_axiom() -> None:
    d = {
        "TelemetryName": "PowerW",
        "Quantity": "Temperature",
        "TypeName": "spaceheat.telemetry.quantity.projection",
        "Version": "000",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        SpaceheatTelemetryQuantityProjection.model_validate(d)

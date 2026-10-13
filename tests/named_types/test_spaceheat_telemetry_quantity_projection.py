"""Tests spaceheat.telemetry.quantity.projection type, version 000"""


from gwsproto.named_types import SpaceheatTelemetryQuantityProjection
from tests.named_types.sema_oracle import assert_refused


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

    assert_refused(SpaceheatTelemetryQuantityProjection, d, match="Axiom 1 violated!")

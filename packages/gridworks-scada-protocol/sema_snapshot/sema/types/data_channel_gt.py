from typing import Literal
from pydantic import ValidationError, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.enums.old_versions.quantity_000 import Quantity000
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.spaceheat_telemetry_quantity_projection import (
    SpaceheatTelemetryQuantityProjection,
)


class DataChannelGt(SemaType):
    """Sema: https://schemas.electricity.works/types/data.channel.gt/003"""

    name: SpaceheatName
    display_name: str
    about_node_name: SpaceheatName
    captured_by_node_name: SpaceheatName
    telemetry_name: TelemetryName
    quantity: Quantity000
    terminal_asset_alias: LeftRightDot
    start_s: UTCSeconds | None = None
    id: UUID4Str
    type_name: Literal["data.channel.gt"] = "data.channel.gt"
    version: Literal["003"] = "003"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "DataChannelGt":
        """
        Axiom 1: TelemetryQuantityConsistency
        Quantity SHALL equal the Quantity defined by the canonical
        spaceheat.telemetry.quantity.projection/000 instance for the specified
        TelemetryName.
        """
        try:
            SpaceheatTelemetryQuantityProjection(
                telemetry_name=self.telemetry_name,
                quantity=self.quantity,
            )
        except ValidationError as e:
            raise ValueError(
                "Axiom 1 failed: quantity is inconsistent with telemetry_name."
            ) from e
        return self

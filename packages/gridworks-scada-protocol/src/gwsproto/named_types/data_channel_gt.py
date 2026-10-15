from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import TelemetryName, Quantity
from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UTCSeconds,
    UUID4Str,
)
from gwsproto.named_types.spaceheat_telemetry_quantity_projection import (
    SpaceheatTelemetryQuantityProjection,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DataChannelGt(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/data.channel.gt/004
    """

    Name: SpaceheatName
    DisplayName: str
    AboutNodeName: SpaceheatName
    CapturedByNodeName: SpaceheatName
    TelemetryName: TelemetryName
    Quantity: Quantity
    TerminalAssetAlias: LeftRightDotStr
    StartS: UTCSeconds | None = None
    Id: UUID4Str
    TypeName: Literal["data.channel.gt"] = "data.channel.gt"
    Version: Literal["004"] = "004"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: TelemetryQuantityConsistency

        Quantity SHALL equal the Quantity defined by the canonical
        spaceheat.telemetry.quantity.projection/001 instance
        for the specified TelemetryName.
        """
        expected_quantity = SpaceheatTelemetryQuantityProjection.canonical(
            self.TelemetryName
        ).Quantity
        if self.Quantity != expected_quantity:
            raise ValueError(
                "Axiom 1 violated! "
                f"TelemetryName {self.TelemetryName} requires Quantity "
                f"{expected_quantity}, not {self.Quantity}"
            )
        return self

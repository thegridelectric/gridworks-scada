from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.enums import TelemetryName, GwQuantity
from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UTCSeconds,
    UUID4Str,
)
from gwsproto.named_types.spaceheat_telemetry_quantity_projection import (
    SpaceheatTelemetryQuantityProjection,
)

class DataChannelGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/data.channel.gt/002
    """

    Name: SpaceheatName
    DisplayName: str
    AboutNodeName: SpaceheatName
    CapturedByNodeName: SpaceheatName
    TelemetryName: TelemetryName
    Quantity: GwQuantity
    TerminalAssetAlias: LeftRightDotStr
    InPowerMetering: bool | None = None
    StartS: UTCSeconds | None = None
    Id: UUID4Str
    TypeName: Literal["data.channel.gt"] = "data.channel.gt"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Power Metering.
        If InPowerMetering is true then the TelemetryName must be PowerW
        """
        if self.InPowerMetering and self.TelemetryName != TelemetryName.PowerW:
            raise ValueError(
                "Axiom 1 violated! If InPowerMetering is true then "
                f"the TelemetryName must be PowerW. Got {self.TelemetryName}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: TelemetryQuantityConsistency

        Quantity SHALL equal the Quantity defined by the canonical
        spaceheat.telemetry.quantity.projection/000 instance
        for the specified TelemetryName.
        """
        expected_quantity = SpaceheatTelemetryQuantityProjection.canonical(
            self.TelemetryName
        ).Quantity
        if self.Quantity != expected_quantity:
            raise ValueError(
                "Axiom 2 violated! "
                f"TelemetryName {self.TelemetryName} requires Quantity "
                f"{expected_quantity}, not {self.Quantity}"
            )
        return self

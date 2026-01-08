from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import TelemetryName
from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UTCSeconds,
    UUID4Str,
)


class DataChannelGt(BaseModel):
    Name: SpaceheatName
    DisplayName: str
    AboutNodeName: SpaceheatName
    CapturedByNodeName: SpaceheatName
    TelemetryName: TelemetryName
    TerminalAssetAlias: LeftRightDotStr
    InPowerMetering: bool | None = None
    StartS: UTCSeconds | None = None
    Id: UUID4Str
    TypeName: Literal["data.channel.gt"] = "data.channel.gt"
    Version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Power Metering.
        If InPowerMetering is true then the TelemetryName must be PowerW
        """
        if self.InPowerMetering and self.TelemetryName != TelemetryName.PowerW:
            raise ValueError(
                "Axiom 1 violated! If InPowerMetering is true then"
                f"the TelemetryName must be PowerW. Got  {self.TelemetryName}"
            )
        return self

    model_config = ConfigDict(use_enum_values=True)

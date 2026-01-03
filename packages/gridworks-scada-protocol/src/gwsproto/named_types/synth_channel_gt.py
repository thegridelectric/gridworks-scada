"""Type synth.channel.gt, version 000"""

from typing import Literal

from pydantic import BaseModel, PositiveInt

from gwsproto.enums import TelemetryName
from gwsproto.property_format import (
    LeftRightDotStr,
    SpaceheatName,
    UUID4Str,
)


class SynthChannelGt(BaseModel):
    """
    Synthesized Channel.

    A descriptor for time-series data channel synthesized from multiple sources (instead of
    the raw telemetry captured by data.channel.gt
    """

    Id: UUID4Str
    Name: SpaceheatName
    CreatedByNodeName: SpaceheatName
    TelemetryName: TelemetryName
    TerminalAssetAlias: LeftRightDotStr
    Strategy: str
    DisplayName: str
    SyncReportMinutes: PositiveInt
    TypeName: Literal["synth.channel.gt"] = "synth.channel.gt"
    Version: Literal["000"] = "000"

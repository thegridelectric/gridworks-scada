from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt

from gwsproto.property_format import (
    SpaceheatName,
    UTCMilliseconds,
)


class SingleReading(BaseModel):
    ChannelName: SpaceheatName
    Value: StrictInt
    ScadaReadTimeUnixMs: UTCMilliseconds
    TypeName: Literal["single.reading"] = "single.reading"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

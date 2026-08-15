from typing import Literal

from pydantic import ConfigDict, StrictInt

from gwsproto.property_format import (
    SpaceheatName,
    UTCMilliseconds,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SingleReading(GwsprotoSemaType):
    ChannelName: SpaceheatName
    Value: StrictInt
    ScadaReadTimeUnixMs: UTCMilliseconds
    TypeName: Literal["single.reading"] = "single.reading"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

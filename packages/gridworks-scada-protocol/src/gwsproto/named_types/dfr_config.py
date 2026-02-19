from typing import Literal

from pydantic import PositiveInt, StrictInt

from gwsproto.named_types import ChannelConfig


class DfrConfig(ChannelConfig):
    OutputIdx: PositiveInt
    InitialVoltsTimes100: StrictInt
    TypeName: Literal["dfr.config"] = "dfr.config"
    Version: Literal["000"] = "000"

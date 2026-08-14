from typing import Literal

from pydantic import BaseModel, PositiveInt, StrictInt

from gwsproto.property_format import SpaceheatName


class DfrConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/dfr.config/000"""

    ChannelName: SpaceheatName
    OutputIdx: PositiveInt
    InitialVoltsTimes100: StrictInt
    TypeName: Literal["dfr.config"] = "dfr.config"
    Version: Literal["000"] = "000"

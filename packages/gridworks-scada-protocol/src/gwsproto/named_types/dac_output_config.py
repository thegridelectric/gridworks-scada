from typing import Literal

from gwsproto.enums import I2cDacChannel
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DacOutputConfig(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/dac.output.config/000"""

    ChannelName: SpaceheatName
    ActorName: SpaceheatName
    DacChannel: I2cDacChannel
    TypeName: Literal["dac.output.config"] = "dac.output.config"
    Version: Literal["000"] = "000"

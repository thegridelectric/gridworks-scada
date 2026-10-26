from typing import Literal

from pydantic import PositiveInt, StrictInt

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DfrConfig(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/dfr.config/000"""

    ChannelName: SpaceheatName
    OutputIdx: PositiveInt
    InitialVoltsTimes100: StrictInt
    TypeName: Literal["dfr.config"] = "dfr.config"
    Version: Literal["000"] = "000"

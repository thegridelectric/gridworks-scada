from typing import Literal, Optional

from gwsproto.named_types.egauge_register_config import (
    EgaugeRegisterConfig as EgaugeConfig,
)
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ElectricMeterChannelConfig(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/electric.meter.channel.config/000"""

    ChannelName: SpaceheatName
    EgaugeRegisterConfig: Optional[EgaugeConfig] = None
    TypeName: Literal["electric.meter.channel.config"] = "electric.meter.channel.config"
    Version: Literal["000"] = "000"

from typing import Literal, Optional

from pydantic import BaseModel

from gwsproto.named_types.egauge_register_config import (
    EgaugeRegisterConfig as EgaugeConfig,
)
from gwsproto.property_format import SpaceheatName


class ElectricMeterChannelConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/electric.meter.channel.config/000"""

    ChannelName: SpaceheatName
    EgaugeRegisterConfig: Optional[EgaugeConfig] = None
    TypeName: Literal["electric.meter.channel.config"] = "electric.meter.channel.config"
    Version: Literal["000"] = "000"

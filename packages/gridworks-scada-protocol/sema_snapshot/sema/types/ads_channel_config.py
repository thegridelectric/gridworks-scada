from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ThermistorDataMethod
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class AdsChannelConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/ads.channel.config/000"""

    channel_name: SpaceheatName
    terminal_block_idx: PositiveInt
    thermistor_device_type: PascalCase
    data_processing_method: ThermistorDataMethod | None = None
    data_processing_description: str | None = None
    type_name: Literal["ads.channel.config"] = "ads.channel.config"
    version: Literal["000"] = "000"

from collections.abc import Sequence
from typing import Literal

from pydantic import PositiveInt, field_validator

from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.named_types.electric_meter_channel_config import ElectricMeterChannelConfig


class ElectricMeterComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/electric.meter.component.gt/001"""

    ModbusHost: str | None = None
    ModbusPort: PositiveInt | None = None
    ConfigList: Sequence[ElectricMeterChannelConfig]
    TypeName: Literal["electric.meter.component.gt"] = "electric.meter.component.gt"
    Version: Literal["001"] = "001"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(
        cls, v: Sequence[ElectricMeterChannelConfig]
    ) -> Sequence[ElectricMeterChannelConfig]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

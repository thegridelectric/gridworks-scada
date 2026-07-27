from collections.abc import Sequence
from typing import Literal, Self

from pydantic import PositiveInt, field_validator, model_validator

from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.named_types.electric_meter_channel_config import ElectricMeterChannelConfig


class ElectricMeterComponentGt(DeviceComponentBase):
    ModbusHost: str | None = None
    ModbusPort: PositiveInt | None = None
    ConfigList: Sequence[ElectricMeterChannelConfig]
    TypeName: Literal["electric.meter.component.gt"] = "electric.meter.component.gt"
    Version: Literal["002"] = "002"

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

    @field_validator("ConfigList")
    @classmethod
    def check_electric_meter_config_list(
        cls, v: list[ElectricMeterChannelConfig]
    ) -> list[ElectricMeterChannelConfig]:
        """Axiom 2: Egauge Config consistency. If one of the ElectricMeterChannelConfigs has an EgaugeRegisterConfig, then they all do."""
        # Implement Axiom(s)
        return v

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: Modbus consistency.
        ModbusHost is None if and only if ModbusPort is None
        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: Egauge4030 Means Modbus.
        If any of the ElectricMeterChannelConfigs have EgaugeRegisterConfig, then the ModbusHost
        is not None
        """
        # Implement check for axiom 2"
        return self

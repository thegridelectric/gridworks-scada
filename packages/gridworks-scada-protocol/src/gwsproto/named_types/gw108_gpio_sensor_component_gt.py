from typing import Literal

from pydantic import PositiveInt, field_validator

from gwsproto.enums import GpioSenseMode
from gwsproto.named_types import ChannelConfig
from gwsproto.type_helpers.component_base import ComponentBase


class Gw108GpioSensorComponentGt(ComponentBase):
    GpioPin: PositiveInt
    SenseMode: GpioSenseMode = GpioSenseMode.Polling
    SendToDerived: bool = False

    TypeName: Literal["gw108.gpio.sensor.component.gt"] = "gw108.gpio.sensor.component.gt"
    Version: Literal["002"] = "002"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[ChannelConfig]) -> list[ChannelConfig]:
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
    def check_axiom_2(cls, v: list[ChannelConfig]) -> list[ChannelConfig]:
        """Axiom 2: exactly one ChannelConfig."""
        if len(v) != 1:
            raise ValueError(
                "Gw108GpioSensorComponentGt must define exactly one ChannelConfig"
            )
        return v

from typing import Literal

from pydantic import PositiveInt, field_validator

from gwsproto.enums import GpioSenseMode
from gwsproto.named_types import ComponentGt, ChannelConfig


class Gw108GpioSensorComponentGt(ComponentGt):
    GpioPin: PositiveInt
    SenseMode: GpioSenseMode = GpioSenseMode.Polling
    SendToDerived: bool = False

    TypeName: Literal["gw108.gpio.sensor.component.gt"] = "gw108.gpio.sensor.component.gt"
    Version: Literal["001"] = "001"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[ChannelConfig]) -> list[ChannelConfig]:
        if len(v) != 1:
            raise ValueError(
                "Gw108GpioSensorComponentGt must define exactly one ChannelConfig"
            )
        return v

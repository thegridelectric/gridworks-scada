from typing import Literal

from pydantic import field_validator

from gwsproto.enums import GpioSenseMode
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.property_format import PascalCase
from gwsproto.type_helpers.component_base import BoardResidentComponentBase


class GpioSensorComponentGt(BoardResidentComponentBase):
    """
    Sema: https://schemas.electricity.works/types/gpio.sensor.component.gt/000
    """

    GpioName: PascalCase
    SenseMode: GpioSenseMode

    TypeName: Literal["gpio.sensor.component.gt"] = "gpio.sensor.component.gt"
    Version: Literal["000"] = "000"

    @field_validator("ConfigList")
    @classmethod
    def check_config_list(cls, v: list[CaptureTuning]) -> list[CaptureTuning]:
        """Runtime shape: exactly one CaptureTuning, spliced on by the ops
        fold (the static word carries no ConfigList)."""
        if len(v) != 1:
            raise ValueError(
                "GpioSensorComponentGt must carry exactly one CaptureTuning"
            )
        return v

from typing import Literal

from gwsproto.enums import GpioSenseMode
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

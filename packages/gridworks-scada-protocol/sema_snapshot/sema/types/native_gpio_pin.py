from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase


class NativeGpioPin(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.native.gpio.pin/000"""

    name: PascalCase
    bcm_pin: NonNegativeInt
    type_name: Literal["gw.native.gpio.pin"] = "gw.native.gpio.pin"
    version: Literal["000"] = "000"

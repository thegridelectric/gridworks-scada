from typing import Literal

from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class NativeGpioPin(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.native.gpio.pin/000"""

    Name: PascalCase
    BcmPin: NonNegativeInt
    TypeName: Literal["gw.native.gpio.pin"] = "gw.native.gpio.pin"
    Version: Literal["000"] = "000"

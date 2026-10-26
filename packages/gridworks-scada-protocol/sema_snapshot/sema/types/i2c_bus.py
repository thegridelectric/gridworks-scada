from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase


class I2cBus(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.bus/000"""

    name: PascalCase
    bus_number: NonNegativeInt
    type_name: Literal["i2c.bus"] = "i2c.bus"
    version: Literal["000"] = "000"

"""Type price.quantity.unitless, version 000"""

from typing import Literal

from pydantic import BaseModel, StrictInt


class PriceQuantityUnitless(BaseModel):
    PriceTimes1000: StrictInt
    QuantityTimes1000: StrictInt
    TypeName: Literal["price.quantity.unitless"] = "price.quantity.unitless"
    Version: Literal["000"] = "000"

from typing import Literal

from pydantic import BaseModel, StrictInt


class PriceQuantityUnitless(BaseModel):
    PriceX1000: StrictInt
    QuantityX1000: StrictInt
    TypeName: Literal["price.quantity.unitless"] = "price.quantity.unitless"
    Version: str = "001"

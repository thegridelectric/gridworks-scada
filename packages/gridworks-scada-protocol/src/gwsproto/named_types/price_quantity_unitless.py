from typing import Literal

from pydantic import StrictInt

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class PriceQuantityUnitless(GwsprotoSemaType):
    PriceX1000: StrictInt
    QuantityX1000: StrictInt
    TypeName: Literal["price.quantity.unitless"] = "price.quantity.unitless"
    Version: str = "001"

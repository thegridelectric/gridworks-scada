from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType


class PriceQuantityUnitless(SemaType):
    """Sema: https://schemas.electricity.works/types/price.quantity.unitless/001"""

    price_x1000: StrictInt
    quantity_x1000: StrictInt
    type_name: Literal["price.quantity.unitless"] = "price.quantity.unitless"
    version: Literal["001"] = "001"

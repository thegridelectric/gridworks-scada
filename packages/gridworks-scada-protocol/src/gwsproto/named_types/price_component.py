from typing import Literal

from pydantic import StrictInt

from gwsproto.enums import PriceComponentName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class PriceComponent(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/price.component/000"""

    Name: PriceComponentName
    PriceX1000: StrictInt
    TypeName: Literal["price.component"] = "price.component"
    Version: Literal["000"] = "000"

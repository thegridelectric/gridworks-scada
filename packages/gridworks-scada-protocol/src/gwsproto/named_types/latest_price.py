from typing import Literal

from gwsproto.enums import MarketPriceUnit
from gwsproto.property_format import LeftRightDotStr, MarketSlotName, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import StrictInt


class LatestPrice(GwsprotoSemaType):
    FromGNodeAlias: LeftRightDotStr
    PriceTimes1000: StrictInt
    PriceUnit: MarketPriceUnit
    MarketSlotName: MarketSlotName
    MessageId: UUID4Str
    TypeName: Literal["latest.price"] = "latest.price"
    Version: Literal["000"] = "000"

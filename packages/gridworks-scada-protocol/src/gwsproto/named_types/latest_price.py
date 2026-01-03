from typing import Literal

from gwsproto.enums import MarketPriceUnit
from gwsproto.property_format import LeftRightDotStr, MarketSlotName, UUID4Str
from pydantic import BaseModel, StrictInt


class LatestPrice(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    PriceTimes1000: StrictInt
    PriceUnit: MarketPriceUnit
    MarketSlotName: MarketSlotName
    MessageId: UUID4Str
    TypeName: Literal["latest.price"] = "latest.price"
    Version: Literal["000"] = "000"

"""Tests latest.price type, version 000"""

import json

from gwsproto.enums import MarketPriceUnit
from gwsproto.named_types import LatestPrice


def test_latest_price_generated() -> None:
    d = {
        "FromGNodeAlias": "d1.isone.ver.keene",
        "PriceTimes1000": 32134,
        "PriceUnit": "USDPerMWh",
        "MarketSlotName": "e.rt60gate5.d1.isone.ver.keene.1577854800",
        "MessageId": "03d27b8e-f6b3-40c5-afe8-880d12921710",
        "TypeName": "latest.price",
        "Version": "000",
    }

    t = LatestPrice.model_validate(d).model_dump_json(exclude_none=True)
    d2 = json.loads(t)
    assert d2 == d

    ######################################
    # Enum related
    ######################################

    assert type(d2["PriceUnit"]) is str

    d2 = dict(d, PriceUnit="unknown_enum_thing")
    assert LatestPrice(**d2).PriceUnit == MarketPriceUnit.default()

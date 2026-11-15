"""Tests price.component type, version 000"""

import json

from gwsproto.enums import PriceComponentName
from gwsproto.named_types import PriceComponent


def test_price_component_generated() -> None:
    d = {
        "Name": "WholesaleCongestion",
        "PriceX1000": -12340,
        "TypeName": "price.component",
        "Version": "000",
    }

    t = PriceComponent.model_validate(d).model_dump_json(exclude_none=True)
    d2 = json.loads(t)
    assert d2 == d

    ######################################
    # Enum related
    ######################################

    assert type(d2["Name"]) is str

    d2 = dict(d, Name="unknown_enum_thing")
    assert PriceComponent(**d2).Name == PriceComponentName.default()

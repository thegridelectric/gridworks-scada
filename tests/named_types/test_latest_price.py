"""Tests latest.price type, version 001"""

import json

from gwsproto.enums import MarketPriceUnit
from gwsproto.named_types import LatestPrice
from tests.named_types.sema_oracle import assert_refused


def component(name: str, price_x1000: int) -> dict:
    return {
        "Name": name,
        "PriceX1000": price_x1000,
        "TypeName": "price.component",
        "Version": "000",
    }


def latest_price_dict() -> dict:
    return {
        "FromGNodeAlias": "d1.isone.ver.keene",
        "PriceX1000": 89896,
        "PriceUnit": "USDPerMWh",
        "MarketSlotName": "e.rt60gate5.d1.isone.ver.keene.1577854800",
        "Components": [
            component("WholesaleEnergy", 32120),
            component("WholesaleCongestion", 40),
            component("WholesaleLoss", -820),
            component("Delivery", 58556),
        ],
        "TariffAlias": "versant.a1.home.eco.bonus",
        "CreatedMs": 1577854805350,
        "MessageId": "03d27b8e-f6b3-40c5-afe8-880d12921710",
        "TypeName": "latest.price",
        "Version": "001",
    }


def test_latest_price_generated() -> None:
    d = latest_price_dict()
    t = LatestPrice.model_validate(d).model_dump_json(exclude_none=True)
    d2 = json.loads(t)
    assert d2 == d

    ######################################
    # Enum related
    ######################################

    assert type(d2["PriceUnit"]) is str

    d2 = dict(d, PriceUnit="unknown_enum_thing")
    assert LatestPrice(**d2).PriceUnit == MarketPriceUnit.default()


def test_latest_price_axiom_1_empty_components() -> None:
    d = latest_price_dict()
    d["Components"] = []
    d.pop("TariffAlias")
    assert_refused(LatestPrice, d, match="Axiom 1")


def test_latest_price_axiom_1_components_do_not_sum() -> None:
    d = latest_price_dict()
    d["PriceX1000"] = 89897
    assert_refused(LatestPrice, d, match="Axiom 1")


def test_latest_price_axiom_2_named_component_twice() -> None:
    d = latest_price_dict()
    d["Components"][1] = component("WholesaleEnergy", 40)
    assert_refused(LatestPrice, d, match="Axiom 2")


def test_latest_price_axiom_2_unknown_may_repeat() -> None:
    d = latest_price_dict()
    d["Components"][1] = component("Unknown", 20)
    d["Components"][2] = component("Unknown", -800)
    assert LatestPrice.model_validate(d).PriceX1000 == 89896


def test_latest_price_axiom_3_delivery_without_tariff() -> None:
    d = latest_price_dict()
    d.pop("TariffAlias")
    assert_refused(LatestPrice, d, match="Axiom 3")


def test_latest_price_axiom_3_tariff_without_delivery() -> None:
    d = latest_price_dict()
    d["Components"] = [component("WholesaleEnergy", 89896)]
    assert_refused(LatestPrice, d, match="Axiom 3")

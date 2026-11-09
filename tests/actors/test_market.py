"""The LTN forms its market facts from the ops word: the slot it bids on,
whether that slot is the current hour, and the topic the maker's latest
price arrives on."""

import json
from pathlib import Path

from actors.ltn.market import latest_price_topic, market_slot_name, slot_is_current
from gwsproto.named_types import OperationalParams

CONFIG = Path(__file__).resolve().parents[1] / "config"


def ops() -> OperationalParams:
    return OperationalParams.model_validate(
        json.loads((CONFIG / "gw.house0.willow.operational.params.json").read_text())
    )


def test_the_slot_is_the_ops_words_maker_and_product_at_the_start() -> None:
    assert market_slot_name(ops(), 1762178400) == "e.rt60gate5.hw1.isone.me.versant.keene.1762178400"


def test_the_latest_price_topic_is_the_makers_rjb_key() -> None:
    assert latest_price_topic(ops().MarketMakerAlias) == "rjb/hw1-isone-me-versant-keene/mm/latest-price"


def test_a_slot_is_current_for_its_own_hour() -> None:
    start = 1762178400
    slot = market_slot_name(ops(), start)
    assert slot_is_current(slot, start)
    assert slot_is_current(slot, start + 3599.9)
    assert not slot_is_current(slot, start + 3600)
    assert not slot_is_current(slot, start - 1)

"""The market facts the LTN forms from its ops word: the slot it bids on
and the topic the maker's latest price arrives on."""

from gwsproto.named_types import OperationalParams
from gwsproto.property_format import MarketSlotName, is_market_slot_name

RJB = "rjb"


def market_slot_name(ops: OperationalParams, slot_start_s: int) -> MarketSlotName:
    """The energy slot on the ops word's maker and product starting at
    `slot_start_s`."""
    return is_market_slot_name(f"e.{ops.MarketProductName.value}.{ops.MarketMakerAlias}.{slot_start_s}")


def latest_price_topic(market_maker_alias: str) -> str:
    """The MQTT topic the maker's latest.price broadcast arrives on: its
    rjb routing key with dots as slashes."""
    return f"{RJB}/{market_maker_alias.replace('.', '-')}/mm/latest-price"

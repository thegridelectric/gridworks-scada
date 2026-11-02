"""The market facts the LTN forms from its ops word, the slot it bids on
and the topic the maker's latest price arrives on, and the clearing rule
that turns its bid curve and a cleared price into a quantity."""

from collections.abc import Sequence

from gwsproto.named_types import OperationalParams, PriceQuantityUnitless
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


def cleared_pair_index(
    pq_pairs: Sequence[PriceQuantityUnitless], price_x1000: int
) -> int:
    """The index of the pair a bid curve commits to at a cleared price.

    A pair holds for every price above the next lower pair's price, up to
    and including its own, so the pair that applies is the lowest-priced
    one at or above the cleared price. A price above every pair takes the
    highest-priced pair, the curve's ceiling.
    """
    if not pq_pairs:
        raise ValueError("A bid curve needs at least one pair")
    at_or_above = [i for i, p in enumerate(pq_pairs) if p.PriceX1000 >= price_x1000]
    if at_or_above:
        return min(at_or_above, key=lambda i: pq_pairs[i].PriceX1000)
    return max(range(len(pq_pairs)), key=lambda i: pq_pairs[i].PriceX1000)

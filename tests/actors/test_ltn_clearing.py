"""The LTN's clearing rule reads its bid curve the way the FLO writes it.

A pair holds for every price above the next lower pair's price, up to and
including its own; the pair that applies to a cleared price is the
lowest-priced one at or above it. The breakpoints are where the two
readings differ, so each test sits on one.
"""

import pytest

from actors.ltn.market import cleared_quantity_x1000
from gwsproto.named_types import PriceQuantityUnitless


def pair(price_x1000: int, quantity_x1000: int) -> PriceQuantityUnitless:
    return PriceQuantityUnitless(PriceX1000=price_x1000, QuantityX1000=quantity_x1000)


# As the FLO emits it: first pair at the ceiling, quantities rising as price falls.
CURVE = [pair(30_000, 0), pair(20_000, 2_000), pair(10_000, 5_000)]


@pytest.mark.parametrize(
    "price_x1000, quantity_x1000",
    [
        (20_000, 2_000),  # exactly on a breakpoint: that pair's quantity
        (20_001, 0),  # just above it: the next pair up
        (19_999, 2_000),  # just below it: still this pair
        (10_000, 5_000),  # on the lowest breakpoint
        (-100_000, 5_000),  # below every pair: the lowest-priced pair
        (30_000, 0),  # on the ceiling
        (2_000_000, 0),  # above every pair: the ceiling pair
    ],
)
def test_lowest_priced_pair_at_or_above_the_cleared_price(
    price_x1000: int, quantity_x1000: int
) -> None:
    assert cleared_quantity_x1000(CURVE, price_x1000) == quantity_x1000


def test_pair_order_does_not_matter() -> None:
    assert cleared_quantity_x1000(list(reversed(CURVE)), 15_000) == 2_000


def test_one_pair_is_the_answer_at_every_price() -> None:
    flat = [pair(-100_000, 3_416)]
    for price_x1000 in (-100_000, 86_090, 2_000_000):
        assert cleared_quantity_x1000(flat, price_x1000) == 3_416


def test_empty_curve_is_refused() -> None:
    with pytest.raises(ValueError):
        cleared_quantity_x1000([], 86_090)

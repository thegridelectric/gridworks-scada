from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.enums import MarketProductName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UTCSeconds
from sema_snapshot.sema.property_format import UUID4Str


class PriceForecast(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.price.forecast/000"""

    from_g_node_alias: LeftRightDot
    market_maker_alias: LeftRightDot
    product_name: MarketProductName
    forecast_uid: UUID4Str
    created_ms: UTCMilliseconds
    slot_start_s: list[UTCSeconds]
    price_unit: MarketPriceUnit
    price_x1000_list: list[StrictInt]
    type_name: Literal["gw.price.forecast"] = "gw.price.forecast"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "PriceForecast":
        """
        Axiom 1: SlotGrid
        a. SlotStartS SHALL be non-empty.
        b. SlotStartS SHALL be strictly ascending.
        c. Every value of SlotStartS SHALL be divisible by 300.
        """
        starts = self.slot_start_s
        if len(starts) == 0:
            raise ValueError(
                "Axiom 1 (SlotGrid, clause a) failed: SlotStartS must be non-empty."
            )
        for earlier, later in zip(starts, starts[1:]):
            if later <= earlier:
                raise ValueError(
                    "Axiom 1 (SlotGrid, clause b) failed: SlotStartS must be "
                    f"strictly ascending; {later} follows {earlier}."
                )
        off_grid = [s for s in starts if s % 300 != 0]
        if off_grid:
            raise ValueError(
                "Axiom 1 (SlotGrid, clause c) failed: every slot start must be "
                f"divisible by 300; got {off_grid!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "PriceForecast":
        """
        Axiom 2: OnePricePerSlot
        len(PriceX1000List) SHALL equal len(SlotStartS).
        """
        prices = len(self.price_x1000_list)
        slots = len(self.slot_start_s)
        if prices != slots:
            raise ValueError(
                "Axiom 2 (OnePricePerSlot) failed: PriceX1000List has "
                f"{prices} values for {slots} slots."
            )
        return self

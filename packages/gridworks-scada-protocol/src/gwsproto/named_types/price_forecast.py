from typing import List, Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import MarketPriceUnit, MarketProductName
from gwsproto.property_format import LeftRightDotStr, UTCMilliseconds, UTCSeconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class PriceForecast(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.price.forecast/000"""

    FromGNodeAlias: LeftRightDotStr
    MarketMakerAlias: LeftRightDotStr
    ProductName: MarketProductName
    ForecastUid: UUID4Str
    CreatedMs: UTCMilliseconds
    SlotStartS: List[UTCSeconds]
    PriceUnit: MarketPriceUnit
    PriceX1000List: List[StrictInt]
    TypeName: Literal["gw.price.forecast"] = "gw.price.forecast"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: SlotGrid.
        a. SlotStartS SHALL be non-empty.
        b. SlotStartS SHALL be strictly ascending.
        c. Every value of SlotStartS SHALL be divisible by 300.
        """
        starts = self.SlotStartS
        if len(starts) == 0:
            raise ValueError("Axiom 1 (SlotGrid) clause a failed: SlotStartS must be non-empty.")
        for earlier, later in zip(starts, starts[1:]):
            if later <= earlier:
                raise ValueError(
                    "Axiom 1 (SlotGrid) clause b failed: SlotStartS must be "
                    f"strictly ascending; {later} follows {earlier}."
                )
        off_grid = [s for s in starts if s % 300 != 0]
        if off_grid:
            raise ValueError(
                "Axiom 1 (SlotGrid) clause c failed: every slot start must be "
                f"divisible by 300; got {off_grid!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: OnePricePerSlot.
        len(PriceX1000List) SHALL equal len(SlotStartS).
        """
        prices = len(self.PriceX1000List)
        slots = len(self.SlotStartS)
        if prices != slots:
            raise ValueError(
                f"Axiom 2 (OnePricePerSlot) failed: PriceX1000List has {prices} values for {slots} slots."
            )
        return self

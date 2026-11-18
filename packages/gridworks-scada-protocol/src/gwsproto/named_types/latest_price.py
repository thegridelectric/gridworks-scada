from typing import List, Literal, Optional

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import MarketPriceUnit, PriceComponentName, PriceStage
from gwsproto.named_types.price_component import PriceComponent
from gwsproto.property_format import LeftRightDotStr, MarketSlotName, UTCMilliseconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class LatestPrice(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/latest.price/002"""

    FromGNodeAlias: LeftRightDotStr
    PriceX1000: StrictInt
    PriceUnit: MarketPriceUnit
    MarketSlotName: MarketSlotName
    PriceStage: PriceStage
    Components: List[PriceComponent]
    TariffAlias: Optional[LeftRightDotStr] = None
    CreatedMs: Optional[UTCMilliseconds] = None
    MessageId: UUID4Str
    TypeName: Literal["latest.price"] = "latest.price"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ComponentsSumToPrice.
        a. Components is non-empty.
        b. The PriceX1000 values of Components sum to PriceX1000.
        """
        if not self.Components:
            raise ValueError("Axiom 1 (ComponentsSumToPrice) failed: Components is empty")
        total = sum(c.PriceX1000 for c in self.Components)
        if total != self.PriceX1000:
            raise ValueError(
                f"Axiom 1 (ComponentsSumToPrice) failed: components sum to {total}, "
                f"PriceX1000 is {self.PriceX1000}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: DistinctNamedComponents. No Name other than Unknown appears
        more than once in Components.
        """
        seen: set[PriceComponentName] = set()
        for c in self.Components:
            if c.Name is PriceComponentName.Unknown:
                continue
            if c.Name in seen:
                raise ValueError(
                    f"Axiom 2 (DistinctNamedComponents) failed: {c.Name} appears twice"
                )
            seen.add(c.Name)
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: TariffWithDelivery. TariffAlias is present exactly when
        Components has a Delivery component.
        """
        has_delivery = any(c.Name is PriceComponentName.Delivery for c in self.Components)
        if has_delivery and self.TariffAlias is None:
            raise ValueError(
                "Axiom 3 (TariffWithDelivery) failed: a Delivery component without TariffAlias"
            )
        if not has_delivery and self.TariffAlias is not None:
            raise ValueError(
                "Axiom 3 (TariffWithDelivery) failed: TariffAlias without a Delivery component"
            )
        return self

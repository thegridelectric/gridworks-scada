from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import MarketSlotName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.price_component import PriceComponent


class LatestPrice(SemaType):
    """Sema: https://schemas.electricity.works/types/latest.price/001"""

    from_g_node_alias: LeftRightDot
    price_x1000: StrictInt
    price_unit: MarketPriceUnit
    market_slot_name: MarketSlotName
    components: list[PriceComponent]
    tariff_alias: LeftRightDot | None = None
    created_ms: UTCMilliseconds | None = None
    message_id: UUID4Str
    type_name: Literal["latest.price"] = "latest.price"
    version: Literal["001"] = "001"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "LatestPrice":
        """
        Axiom 1: ComponentsSumToPrice
        a. Components SHALL be non-empty.
        b. The PriceX1000 values of Components SHALL sum to PriceX1000.
        """
        if len(self.components) == 0:
            raise ValueError(
                "Axiom 1 (ComponentsSumToPrice, clause a) failed: Components must "
                "be non-empty."
            )
        total = sum(c.price_x1000 for c in self.components)
        if total != self.price_x1000:
            raise ValueError(
                "Axiom 1 (ComponentsSumToPrice, clause b) failed: the components "
                f"sum to {total}, PriceX1000 is {self.price_x1000}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "LatestPrice":
        """
        Axiom 2: DistinctNamedComponents
        No Name other than Unknown SHALL appear more than once in Components.
        """
        names = [c.name.value for c in self.components if c.name.value != "Unknown"]
        if len(set(names)) != len(names):
            raise ValueError(
                "Axiom 2 (DistinctNamedComponents) failed: a Name other than "
                f"Unknown appears more than once; got {names!r}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "LatestPrice":
        """
        Axiom 3: TariffWithDelivery
        a. If Components has a component named Delivery, TariffAlias SHALL be present.
        b. If Components has no component named Delivery, TariffAlias SHALL be absent.
        """
        has_delivery = any(c.name.value == "Delivery" for c in self.components)
        if has_delivery and self.tariff_alias is None:
            raise ValueError(
                "Axiom 3 (TariffWithDelivery, clause a) failed: a Delivery "
                "component needs TariffAlias."
            )
        if not has_delivery and self.tariff_alias is not None:
            raise ValueError(
                "Axiom 3 (TariffWithDelivery, clause b) failed: TariffAlias "
                f"{self.tariff_alias!r} is given with no Delivery component."
            )
        return self

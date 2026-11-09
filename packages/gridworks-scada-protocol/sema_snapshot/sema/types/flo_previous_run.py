from typing import Literal, Self
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import MarketPriceUnit
from sema_snapshot.sema.enums import MarketQuantityUnit
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.flo_optimal_path import FloOptimalPath
from sema_snapshot.sema.types.price_quantity_unitless import PriceQuantityUnitless


class FloPreviousRun(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.previous.run/000"""

    path: FloOptimalPath
    cleared_pair_index: NonNegativeInt
    cleared_pair: PriceQuantityUnitless
    price_unit: MarketPriceUnit
    quantity_unit: MarketQuantityUnit
    next_slot_price_x1000: StrictInt
    created_ms: UTCMilliseconds
    type_name: Literal["flo.previous.run"] = "flo.previous.run"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PathStartsAtTheBid
        The first element of Path.HpAvgWList SHALL equal
        ClearedPair.QuantityX1000 expressed in watts: as is when
        QuantityUnit is AvgkW, times 1000 when it is AvgMW.
        """
        to_watts = 1000 if self.quantity_unit.value == "AvgMW" else 1
        if not self.path.hp_avg_w_list:
            raise ValueError("Axiom 1 (PathStartsAtTheBid) failed: Path has no steps.")
        expected = self.cleared_pair.quantity_x1000 * to_watts
        if self.path.hp_avg_w_list[0] != expected:
            raise ValueError(
                f"Axiom 1 (PathStartsAtTheBid) failed: Path.HpAvgWList[0] "
                f"({self.path.hp_avg_w_list[0]} W) must equal ClearedPair.QuantityX1000 "
                f"({expected} W)."
            )
        return self

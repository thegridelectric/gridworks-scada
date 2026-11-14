from typing import Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit
from gwsproto.named_types.flo_optimal_path import FloOptimalPath
from gwsproto.named_types.price_quantity_unitless import PriceQuantityUnitless
from gwsproto.property_format import NonNegativeInt, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloPreviousRun(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.previous.run/000"""

    Path: FloOptimalPath
    ClearedPairIndex: NonNegativeInt
    ClearedPair: PriceQuantityUnitless
    PriceUnit: MarketPriceUnit
    QuantityUnit: MarketQuantityUnit
    NextSlotPriceX1000: StrictInt
    CreatedMs: UTCMilliseconds
    TypeName: Literal["flo.previous.run"] = "flo.previous.run"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: PathStartsAtTheBid.
        The first element of Path.HpAvgWList SHALL equal
        ClearedPair.QuantityX1000 expressed in watts: as is when
        QuantityUnit is AvgkW, times 1000 when it is AvgMW.
        """
        to_watts = 1000 if self.QuantityUnit == MarketQuantityUnit.AvgMW else 1
        if not self.Path.HpAvgWList:
            raise ValueError("Axiom 1 (PathStartsAtTheBid) failed: Path has no steps.")
        expected = self.ClearedPair.QuantityX1000 * to_watts
        if self.Path.HpAvgWList[0] != expected:
            raise ValueError(
                f"Axiom 1 (PathStartsAtTheBid) failed: Path.HpAvgWList[0] "
                f"({self.Path.HpAvgWList[0]} W) must equal ClearedPair.QuantityX1000 "
                f"({expected} W)."
            )
        return self

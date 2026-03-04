from typing import Literal
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.enums.gw_unit import GwUnit
from gwsproto.enums.gw_quantity import GwQuantity


class UnitQuantityProjection(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw1.unit.quantity.projection/000"""

    Unit: GwUnit
    Quantity: GwQuantity
    TypeName: Literal["gw1.unit.quantity.projection"] = "gw1.unit.quantity.projection"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        valid_pairs = {
            GwUnit.Unknown: GwQuantity.Unknown,
            GwUnit.Unitless: GwQuantity.Unitless,
            GwUnit.FahrenheitX100: GwQuantity.Temperature,
            GwUnit.Watts: GwQuantity.Power,
            GwUnit.WattHours: GwQuantity.Energy,
            GwUnit.Gallons: GwQuantity.Volume,
            GwUnit.GpmX100: GwQuantity.FlowRate,
        }

        if valid_pairs.get(self.Unit) != self.Quantity:
            raise ValueError(
                f"Invalid Unit → Quantity projection: {self.Unit} → {self.Quantity}"
            )

        return self
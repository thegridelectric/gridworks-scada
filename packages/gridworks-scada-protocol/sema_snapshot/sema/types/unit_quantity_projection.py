from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import Quantity
from sema_snapshot.sema.enums import Unit


_PROJECTION = {
    Unit.Unknown: Quantity.Unknown,
    Unit.Unitless: Quantity.Unitless,
    Unit.FahrenheitX100: Quantity.Temperature,
    Unit.Watts: Quantity.Power,
    Unit.WattHours: Quantity.Energy,
    Unit.Gallons: Quantity.Volume,
    Unit.GpmX100: Quantity.FlowRate,
    Unit.Seconds: Quantity.Time,
    Unit.SecondsX10: Quantity.Time,
    Unit.Milliseconds: Quantity.Time,
    Unit.DollarsX1000: Quantity.Currency,
    Unit.MilesPerHourX1000: Quantity.WindSpeed,
    Unit.KilowattHoursX1000: Quantity.Energy,
    Unit.WattsPerSquareMeter: Quantity.Irradiance,
    Unit.MilesPerHourX10: Quantity.WindSpeed,
    Unit.FahrenheitX10: Quantity.Temperature,
}


class UnitQuantityProjection(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.unit.quantity.projection/001"""

    unit: Unit
    quantity: Quantity
    type_name: Literal["gw1.unit.quantity.projection"] = "gw1.unit.quantity.projection"
    version: Literal["001"] = "001"

    @classmethod
    def project(cls, unit: Unit) -> Quantity:
        expected = _PROJECTION.get(unit)
        if expected is None:
            raise ValueError(f"No projection defined for unit {unit!r}.")
        return expected

    @model_validator(mode="after")
    def check_axiom_1(self) -> "UnitQuantityProjection":
        """
        Axiom 1: EnumeratedProjectionMapping
        Every (Unit, Quantity) pair SHALL match the mapping declared in
        x-gridworks.projection.table. Any combination not present in the table is invalid.
        """
        expected = self.project(self.unit)
        if expected != self.quantity:
            raise ValueError(
                "Axiom 1 failed: unit and quantity do not match the enumerated projection."
            )
        return self

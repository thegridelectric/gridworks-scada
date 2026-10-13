from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums.old_versions.quantity_001 import Quantity001
from sema_snapshot.sema.enums.old_versions.unit_001 import Unit001


_PROJECTION = {
    Unit001.Unknown: Quantity001.Unknown,
    Unit001.Unitless: Quantity001.Unitless,
    Unit001.FahrenheitX100: Quantity001.Temperature,
    Unit001.Watts: Quantity001.Power,
    Unit001.WattHours: Quantity001.Energy,
    Unit001.Gallons: Quantity001.Volume,
    Unit001.GpmX100: Quantity001.FlowRate,
    Unit001.Seconds: Quantity001.Time,
    Unit001.SecondsX10: Quantity001.Time,
    Unit001.Milliseconds: Quantity001.Time,
}


class UnitQuantityProjection(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.unit.quantity.projection/000"""

    unit: Unit001
    quantity: Quantity001
    type_name: Literal["gw1.unit.quantity.projection"] = "gw1.unit.quantity.projection"
    version: Literal["000"] = "000"

    @classmethod
    def project(cls, unit: Unit001) -> Quantity001:
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

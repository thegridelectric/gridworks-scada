from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import Quantity, Unit
from gwsproto.enums.unit_quantity import UNIT_TO_QUANTITY


class UnitQuantityProjection(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw1.unit.quantity.projection/000

    The canonical (Unit, Quantity) pairing. The quantity a GwUnit measures is
    fixed by the enumerated projection table (gwsproto.enums.unit_quantity), so
    every instance SHALL satisfy Quantity == project(Unit). This is the type
    `derived.channel.gt` axiom 2 reads when binding OutputQuantity to OutputUnit.
    """

    Unit: Unit
    Quantity: Quantity
    TypeName: Literal[
        "gw1.unit.quantity.projection"
    ] = "gw1.unit.quantity.projection"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def project(cls, unit: Unit) -> Quantity:
        expected = UNIT_TO_QUANTITY.get(unit)
        if expected is None:
            raise ValueError(f"No projection defined for unit {unit!r}.")
        return expected

    @classmethod
    def canonical(cls, unit: Unit) -> "UnitQuantityProjection":
        return cls(Unit=unit, Quantity=cls.project(unit))

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: EnumeratedProjectionMapping.
        Quantity must match the canonical projection for Unit.
        """
        expected = self.project(self.Unit)
        if self.Quantity != expected:
            raise ValueError(
                "Axiom 1 violated! "
                f"Unit {self.Unit} maps to Quantity {expected}, not {self.Quantity}"
            )
        return self

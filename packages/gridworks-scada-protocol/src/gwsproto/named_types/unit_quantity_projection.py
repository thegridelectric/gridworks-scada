from typing import Literal

from pydantic import ConfigDict, model_validator
from typing_extensions import Self

from gwsproto.enums import Quantity as GwQuantity, Unit as GwUnit
from gwsproto.enums.unit_quantity import UNIT_TO_QUANTITY
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class UnitQuantityProjection(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw1.unit.quantity.projection/000
    """

    Unit: GwUnit
    Quantity: GwQuantity
    TypeName: Literal[
        "gw1.unit.quantity.projection"
    ] = "gw1.unit.quantity.projection"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def project(cls, unit: GwUnit) -> GwQuantity:
        expected = UNIT_TO_QUANTITY.get(unit)
        if expected is None:
            raise ValueError(f"No projection defined for unit {unit!r}.")
        return expected

    @classmethod
    def canonical(cls, unit: GwUnit) -> "UnitQuantityProjection":
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

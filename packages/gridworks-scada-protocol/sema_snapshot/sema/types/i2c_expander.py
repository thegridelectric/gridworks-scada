from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cExpanderType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt


class I2cExpander(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.expander/000"""

    expander_idx: PositiveInt
    i2c_bus: PascalCase
    expander_type: I2cExpanderType
    i2c_address: NonNegativeInt | None = None
    allowed_i2c_address_list: list[NonNegativeInt] | None = None
    type_name: Literal["i2c.expander"] = "i2c.expander"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cExpander":
        """
        Axiom 1: AddressSpecification
        Exactly one of I2cAddress and AllowedI2cAddressList SHALL be present.
        """
        has_fixed = self.i2c_address is not None
        has_allowed = self.allowed_i2c_address_list is not None
        if has_fixed == has_allowed:
            raise ValueError(
                "Axiom 1 (AddressSpecification) failed: exactly one of "
                "I2cAddress and AllowedI2cAddressList must be present; got "
                f"I2cAddress={self.i2c_address}, "
                f"AllowedI2cAddressList={self.allowed_i2c_address_list}."
            )
        return self

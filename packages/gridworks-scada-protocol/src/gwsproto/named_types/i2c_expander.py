from typing import Literal, Optional

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import NonNegativeInt, PascalCase


class I2cExpander(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.expander/000"""

    ExpanderIdx: PositiveInt
    I2cBus: PascalCase
    I2cAddress: Optional[NonNegativeInt] = None
    AllowedI2cAddressList: Optional[list[NonNegativeInt]] = None
    TypeName: Literal["i2c.expander"] = "i2c.expander"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: AddressSpecification. Exactly one of I2cAddress and
        AllowedI2cAddressList SHALL be present.
        """
        has_fixed = self.I2cAddress is not None
        has_allowed = self.AllowedI2cAddressList is not None
        if has_fixed == has_allowed:
            raise ValueError(
                "Axiom 1 (AddressSpecification) failed: exactly one of "
                "I2cAddress and AllowedI2cAddressList must be present; got "
                f"I2cAddress={self.I2cAddress}, "
                f"AllowedI2cAddressList={self.AllowedI2cAddressList}."
            )
        return self

from typing import Literal, Self

from pydantic import BaseModel, PositiveInt, model_validator

from gwsproto.enums import I2cDacChannel, I2cDacVref
from gwsproto.property_format import NonNegativeInt


class I2cDacChannelConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.dac.channel.config/000"""

    DacChannel: I2cDacChannel
    PowerOnRawValue: NonNegativeInt
    PowerOnVref: I2cDacVref
    PowerOnGain: PositiveInt
    TypeName: Literal["i2c.dac.channel.config"] = "i2c.dac.channel.config"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: EepromRanges
        a. PowerOnRawValue SHALL be less than 4096. b. PowerOnGain SHALL be 1 or 2.
        """
        if self.PowerOnRawValue >= 4096:
            raise ValueError(
                "Axiom 1 (EepromRanges) failed: PowerOnRawValue "
                f"{self.PowerOnRawValue} is not less than 4096."
            )
        if self.PowerOnGain not in (1, 2):
            raise ValueError(
                "Axiom 1 (EepromRanges) failed: PowerOnGain "
                f"{self.PowerOnGain} is not 1 or 2."
            )
        return self

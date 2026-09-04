from typing import Literal, Self

from pydantic import PositiveInt, model_validator

from gwsproto.enums import I2cDacChannel, I2cDacVref
from gwsproto.property_format import NonNegativeInt, SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DacOutputConfig(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/dac.output.config/000"""

    ChannelName: SpaceheatName
    ActorName: SpaceheatName
    DacChannel: I2cDacChannel
    PowerOnRawValue: NonNegativeInt
    PowerOnVref: I2cDacVref
    PowerOnGain: PositiveInt
    TypeName: Literal["dac.output.config"] = "dac.output.config"
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

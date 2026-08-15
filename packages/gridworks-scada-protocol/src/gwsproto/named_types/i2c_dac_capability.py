from typing import Literal, Optional, Self

from pydantic import PositiveInt, model_validator

from gwsproto.enums import I2cDacType
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cDacCapability(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.dac.capability/000"""

    DacName: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    MuxName: Optional[PascalCase] = None
    MuxChannel: Optional[NonNegativeInt] = None
    DacType: I2cDacType
    Channels: PositiveInt
    TypeName: Literal["i2c.dac.capability"] = "i2c.dac.capability"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: MuxPairing
        MuxName and MuxChannel SHALL be both present or both absent.
        """
        if (self.MuxName is None) != (self.MuxChannel is None):
            raise ValueError(
                "Axiom 1 (MuxPairing) failed: MuxName and MuxChannel must be "
                f"both present or both absent; got MuxName={self.MuxName!r}, "
                f"MuxChannel={self.MuxChannel!r}."
            )
        return self

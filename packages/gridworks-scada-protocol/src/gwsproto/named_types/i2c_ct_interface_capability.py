from typing import Literal, Optional, Self

from pydantic import PositiveFloat, PositiveInt, model_validator

from gwsproto.enums import I2cAdcType
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cCtInterfaceCapability(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.ct.interface.capability/000"""

    Name: PascalCase
    I2cBus: PascalCase
    I2cAddress: NonNegativeInt
    AdcType: I2cAdcType
    AdcReferenceVolts: PositiveFloat
    Channels: PositiveInt
    MuxName: Optional[PascalCase] = None
    MuxChannel: Optional[NonNegativeInt] = None
    TypeName: Literal["i2c.ct.interface.capability"] = "i2c.ct.interface.capability"
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

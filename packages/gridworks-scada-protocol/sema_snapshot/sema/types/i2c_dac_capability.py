from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cDacType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveInt


class I2cDacCapability(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.dac.capability/000"""

    dac_name: PascalCase
    i2c_bus: PascalCase
    i2c_address: NonNegativeInt
    mux_name: PascalCase | None = None
    mux_channel: NonNegativeInt | None = None
    dac_type: I2cDacType
    channels: PositiveInt
    type_name: Literal["i2c.dac.capability"] = "i2c.dac.capability"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cDacCapability":
        """
        Axiom 1: MuxPairing
        MuxName and MuxChannel SHALL be both present or both absent.
        """
        if (self.mux_name is None) != (self.mux_channel is None):
            raise ValueError(
                "Axiom 1 (MuxPairing) failed: MuxName and MuxChannel must be "
                f"both present or both absent; got MuxName={self.mux_name!r}, "
                f"MuxChannel={self.mux_channel!r}."
            )
        return self

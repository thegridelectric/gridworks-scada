from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import I2cAdcType
from sema_snapshot.sema.property_format import NonNegativeInt
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import PositiveFloat
from sema_snapshot.sema.property_format import PositiveInt


class I2cCtInterfaceCapability(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.ct.interface.capability/000"""

    name: PascalCase
    i2c_bus: PascalCase
    i2c_address: NonNegativeInt
    adc_type: I2cAdcType
    adc_reference_volts: PositiveFloat
    channels: PositiveInt
    mux_name: PascalCase | None = None
    mux_channel: NonNegativeInt | None = None
    type_name: Literal["i2c.ct.interface.capability"] = "i2c.ct.interface.capability"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cCtInterfaceCapability":
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

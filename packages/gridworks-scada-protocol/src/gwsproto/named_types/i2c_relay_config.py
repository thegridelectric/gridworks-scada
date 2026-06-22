from typing import Literal, Optional

from pydantic import BaseModel

from gwsproto.enums import RelayWiringConfig
from gwsproto.named_types.i2c_bit_address import I2cBitAddress
from gwsproto.property_format import PascalCase


class I2cRelayConfig(BaseModel):
    """Sema: https://schemas.electricity.works/types/i2c.relay.config/000"""

    RelayName: PascalCase
    I2cBus: PascalCase
    Address: I2cBitAddress
    SupportedWiringConfigs: list[RelayWiringConfig]
    Notes: Optional[str] = None
    TypeName: Literal["i2c.relay.config"] = "i2c.relay.config"
    Version: Literal["000"] = "000"

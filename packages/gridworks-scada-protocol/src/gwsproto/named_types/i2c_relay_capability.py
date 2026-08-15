from typing import Literal, Optional

from pydantic import PositiveInt

from gwsproto.enums import RelayWiringConfig
from gwsproto.property_format import NonNegativeInt, PascalCase
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class I2cRelayCapability(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/i2c.relay.capability/000"""

    RelayName: PascalCase
    ExpanderIdx: PositiveInt
    RegisterIndex: NonNegativeInt
    BitIndex: NonNegativeInt
    SupportedWiringConfigs: list[RelayWiringConfig]
    Notes: Optional[str] = None
    TypeName: Literal["i2c.relay.capability"] = "i2c.relay.capability"
    Version: Literal["000"] = "000"

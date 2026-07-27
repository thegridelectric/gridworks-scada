from typing import Literal, Optional

from gwsproto.property_format import NonNegativeInt
from gwsproto.type_helpers.component_base import DeviceComponentBase


class ScadaBoardComponentGt(DeviceComponentBase):
    """
    Sema: https://schemas.electricity.works/types/scada.board.component.gt/000
    """

    I2cAddressList: Optional[list[NonNegativeInt]] = None

    TypeName: Literal["scada.board.component.gt"] = "scada.board.component.gt"
    Version: Literal["000"] = "000"

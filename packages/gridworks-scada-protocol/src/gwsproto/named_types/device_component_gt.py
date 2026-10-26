from typing import Literal, Optional

from gwsproto.type_helpers.component_base import DeviceComponentBase


class DeviceComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/device.component.gt/000"""

    Description: Optional[str] = None
    TypeName: Literal["device.component.gt"] = "device.component.gt"
    Version: Literal["000"] = "000"

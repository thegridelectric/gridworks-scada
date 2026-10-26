from typing import Literal

from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.named_types.hubitat_poller_gt import HubitatPollerGt


class HubitatPollerComponentGt(DeviceComponentBase):
    Poller: HubitatPollerGt
    TypeName: Literal["hubitat.poller.component.gt"] = "hubitat.poller.component.gt"
    Version: Literal["000"] = "000"

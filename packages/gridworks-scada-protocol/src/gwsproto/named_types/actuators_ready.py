
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class ActuatorsReady(GwsprotoSemaType):
    """
    Used to sequence inbound messages to actuators
    """
    TypeName: Literal["actuators.ready"] = "actuators.ready"
    Version: Literal["000"] = "000"

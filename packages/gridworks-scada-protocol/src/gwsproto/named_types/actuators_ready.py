from typing import Literal

from pydantic import BaseModel


class ActuatorsReady(BaseModel):
    """
    Used to sequence inbound messages to actuators
    """
    TypeName: Literal["actuators.ready"] = "actuators.ready"
    Version: Literal["000"] = "000"

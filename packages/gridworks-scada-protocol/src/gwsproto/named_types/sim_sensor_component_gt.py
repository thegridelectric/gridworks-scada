from typing import Literal

from pydantic import ConfigDict

from gwsproto.type_helpers.component_base import DeviceComponentBase


class SimSensorComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/sim.sensor.component.gt/000"""

    TypeName: Literal["sim.sensor.component.gt"] = "sim.sensor.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

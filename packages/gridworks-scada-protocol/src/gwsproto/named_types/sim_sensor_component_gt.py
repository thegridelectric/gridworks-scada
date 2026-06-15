from typing import Literal

from pydantic import ConfigDict

from gwsproto.named_types.component_gt import ComponentGt


class SimSensorComponentGt(ComponentGt):
    """
    A simulated sensor component — what a SimSensorActor uses in a simulated layout.

    Sema word: ``sim.sensor.component.gt``. Structurally the generic component
    (ComponentId, DeviceType, ConfigList of channel.config), but a distinct ``sim.*``
    type so a simulated layout is visibly simulated by construction.
    """

    TypeName: Literal["sim.sensor.component.gt"] = "sim.sensor.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

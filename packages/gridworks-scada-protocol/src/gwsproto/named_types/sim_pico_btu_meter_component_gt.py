from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, StrictInt

from gwsproto.enums import (
    GpmFromHzMethod,
    HzCalcMethod,
    TempCalcMethod,
)
from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.property_format import (
    SpaceheatName,
)


class SimPicoBtuMeterComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/sim.pico.btu.meter.component.gt/000"""

    Enabled: bool
    SerialNumber: str
    FlowChannelName: SpaceheatName
    HotChannelName: SpaceheatName
    ColdChannelName: SpaceheatName
    ReadCtVoltage: bool
    SendHz: bool
    CtChannelName: Optional[SpaceheatName] = None
    FlowMeterType: str
    HzCalcMethod: HzCalcMethod
    TempCalcMethod: TempCalcMethod
    ThermistorBeta: StrictInt
    GpmFromHzMethod: GpmFromHzMethod
    GallonsPerPulse: float
    AsyncCaptureDeltaGpmX100: StrictInt
    AsyncCaptureDeltaCelsiusX100: StrictInt
    AsyncCaptureDeltaCtVoltsX100: Optional[StrictInt] = None
    SimLifeS: Optional[PositiveInt] = None
    SimRebootS: Optional[PositiveInt] = None
    SimulatesTypeName: Literal["pico.btu.meter.component.gt"] = "pico.btu.meter.component.gt"
    SimulatesVersion: Literal["000"] = "000"
    TypeName: Literal["sim.pico.btu.meter.component.gt"] = "sim.pico.btu.meter.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True, extra="allow")

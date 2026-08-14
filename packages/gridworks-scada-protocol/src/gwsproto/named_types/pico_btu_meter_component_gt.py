from typing import Literal, Optional

from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    GpmFromHzMethod,
    HzCalcMethod,
    TempCalcMethod,
)
from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.property_format import (
    SpaceheatName,
)


class PicoBtuMeterComponentGt(DeviceComponentBase):
    """
    Sema: https://schemas.electricity.works/types/pico.btu.meter.component.gt/000
    """

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
    TypeName: Literal["pico.btu.meter.component.gt"] = "pico.btu.meter.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ReadCtVoltage is True iff AsyncCaptureDeltaCtVoltsX100 exists
        """
        if self.ReadCtVoltage and not self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(
                f"Axiom 2 violated! ReadCtVoltage {self.ReadCtVoltage} requires AsyncCaptureDeltaCtVoltsX100!"
            )
        if not self.ReadCtVoltage and self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(
                f"Axiom 2 violated: ReadCtVoltage {self.ReadCtVoltage} means NOAsyncCaptureDeltaCtVoltsX100"
            )
        return self

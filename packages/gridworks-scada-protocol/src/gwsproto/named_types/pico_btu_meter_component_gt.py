from typing import Literal, Optional

from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    GpmFromHzMethod,
    HzCalcMethod,
    MakeModel,
    TempCalcMethod,
)
from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.property_format import (
    SpaceheatName,
)


class PicoBtuMeterComponentGt(ComponentGt):
    Enabled: bool
    SerialNumber: str
    FlowChannelName: SpaceheatName
    HotChannelName: SpaceheatName
    ColdChannelName: SpaceheatName
    ReadCtVoltage: bool
    SendHz: bool
    CtChannelName: Optional[SpaceheatName] = None
    FlowMeterType: MakeModel
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
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ReadCtVoltage is True iff AsyncCaptureDeltaCtVoltsX100 exists
        """
        if self.ReadCtVoltage and not self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(
                f"Axiom 1 violated! ReadCtVoltage {self.ReadCtVoltage} requires AsyncCaptureDeltaCtVoltsX100!"
            )
        if not self.ReadCtVoltage and self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(
                f"Axiom 1 violated: ReadCtVoltage {self.ReadCtVoltage} means NOAsyncCaptureDeltaCtVoltsX100"
            )
        return self

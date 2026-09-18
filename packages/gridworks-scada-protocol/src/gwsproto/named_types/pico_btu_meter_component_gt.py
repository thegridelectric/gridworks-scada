from typing import Literal, Optional

from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    GpmFromHzMethod,
    HzCalcMethod,
    PicoBoardVariant,
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
    PicoBoardVariant: PicoBoardVariant
    MicropythonVersion: Optional[str] = None
    TypeName: Literal["pico.btu.meter.component.gt"] = "pico.btu.meter.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ReadCtVoltageIffCtVoltsDelta.
        ReadCtVoltage is true iff AsyncCaptureDeltaCtVoltsX100 is present.
        """
        if self.ReadCtVoltage != (self.AsyncCaptureDeltaCtVoltsX100 is not None):
            raise ValueError(
                "Axiom 1 (ReadCtVoltageIffCtVoltsDelta) failed: "
                f"ReadCtVoltage {self.ReadCtVoltage}, "
                f"AsyncCaptureDeltaCtVoltsX100 {self.AsyncCaptureDeltaCtVoltsX100}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ReadCtVoltageIffCtChannelName.
        ReadCtVoltage is true iff CtChannelName is present.
        """
        if self.ReadCtVoltage != (self.CtChannelName is not None):
            raise ValueError(
                "Axiom 2 (ReadCtVoltageIffCtChannelName) failed: "
                f"ReadCtVoltage {self.ReadCtVoltage}, CtChannelName {self.CtChannelName}"
            )
        return self

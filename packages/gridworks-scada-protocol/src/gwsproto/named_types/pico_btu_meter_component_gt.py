from collections.abc import Sequence
from typing import Literal, Optional

from pydantic import ConfigDict, StrictInt, field_validator, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    GpmFromHzMethod,
    HzCalcMethod,
    TempCalcMethod,
)
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.type_helpers.component_base import ComponentBase
from gwsproto.property_format import (
    SpaceheatName,
)


class PicoBtuMeterComponentGt(ComponentBase):
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
    Version: Literal["001"] = "001"

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: Sequence[CaptureTuning]) -> Sequence[CaptureTuning]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

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

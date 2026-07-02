import re
from collections.abc import Sequence
from typing import Literal, Optional

from pydantic import field_validator

from gwsproto.enums import GpmFromHzMethod, HzCalcMethod
from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.type_helpers.component_base import ComponentBase
from gwsproto.property_format import SpaceheatName


class PicoFlowModuleComponentGt(ComponentBase):
    Enabled: bool
    SerialNumber: str
    FlowNodeName: SpaceheatName
    FlowMeterType: str = "SaierFlowSensor"
    HzCalcMethod: HzCalcMethod
    GpmFromHzMethod: GpmFromHzMethod
    ConstantGallonsPerTick: float
    SendHz: bool = True
    SendGallons: bool = False
    SendTickLists: bool = False
    NoFlowMs: int
    AsyncCaptureThresholdGpmTimes100: int
    PublishEmptyTicklistAfterS: Optional[int] = None  # Hall Params
    PublishAnyTicklistAfterS: Optional[int] = None  # Reed Params
    PublishTicklistPeriodS: Optional[int] = None  # Required for Hall Params
    PublishTicklistLength: Optional[int] = None  # required for Reed Params
    ExpAlpha: Optional[float] = None
    CutoffFrequency: Optional[float] = None
    TypeName: Literal["pico.flow.module.component.gt"] = "pico.flow.module.component.gt"
    Version: Literal["001"] = "001"

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

    @field_validator("HwUid")
    @classmethod
    def check_hw_uid(cls, v: str) -> str:
        """
        Axiom 2: HwUid is of the form 'pico_xxxxxx' where xxxxxx
        are lowercase hex (the last digits of its pico W hw id)
        """
        pattern = r"^pico_[0-9a-f]{6}$"
        if not bool(re.match(pattern, v)):
            raise ValueError("HwUid should be the pico hwuid, eg pico_60e352")
        return v

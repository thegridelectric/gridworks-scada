"""Type pico.btu.meter.component.gt, version 000"""

from typing import Literal, Optional

from pydantic import BaseModel, StrictInt, field_validator

from gwproto.enums import GpmFromHzMethod, HzCalcMethod, MakeModel, TempCalcMethod
from gwproto.property_format import (
    SpaceheatName,
)


class PicoBtuMeterComponentGt(BaseModel):
    Enabled: bool
    SerialNumber: str
    FlowNodeName: SpaceheatName
    HotNodeName: SpaceheatName
    ColdNodeName: SpaceheatName
    ReadCt: bool
    CtNodeName: Optional[SpaceheatName] = None
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

    @field_validator("HwUid")
    @classmethod
    def check_hw_uid(cls, v: str) -> str:
        """
        Axiom 1: HwUid is of the form 'pico_xxxxxx' where xxxxxx
        are lowercase hex (the last digits of its pico W hw id)
        """
        pattern = r"^pico_[0-9a-f]{6}$"
        if not bool(re.match(pattern, v)):
            raise ValueError("HwUid should be the pico hwuid, eg pico_60e352")
        return v

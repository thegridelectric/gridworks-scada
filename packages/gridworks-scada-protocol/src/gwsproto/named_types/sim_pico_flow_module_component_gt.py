import re
from typing import Literal, Optional

from pydantic import ConfigDict, PositiveInt, field_validator

from gwsproto.enums import GpmFromHzMethod, HzCalcMethod
from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.property_format import SpaceheatName


class SimPicoFlowModuleComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/sim.pico.flow.module.component.gt/000"""

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
    SimLifeS: Optional[PositiveInt] = None
    SimRebootS: Optional[PositiveInt] = None
    SimulatesTypeName: Literal["pico.flow.module.component.gt"] = "pico.flow.module.component.gt"
    SimulatesVersion: Literal["001"] = "001"
    TypeName: Literal["sim.pico.flow.module.component.gt"] = "sim.pico.flow.module.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @field_validator("HwUid")
    @classmethod
    def check_axiom_1(cls, v: str) -> str:
        """
        Axiom 1: HwUidPattern.
        If HwUid is present, it SHALL match the pattern pico_xxxxxx where
        xxxxxx are lowercase hex (the last digits of its pico W hw id)
        """
        pattern = r"^pico_[0-9a-f]{6}$"
        if not bool(re.match(pattern, v)):
            raise ValueError("HwUid should be the pico hwuid, eg pico_60e352")
        return v

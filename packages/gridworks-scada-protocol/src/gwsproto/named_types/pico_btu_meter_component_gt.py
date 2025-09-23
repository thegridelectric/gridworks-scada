import re
from typing import Literal, Optional

from pydantic import field_validator

from gwproto.enums import GpmFromHzMethod, HzCalcMethod, MakeModel
from gwproto.named_types.component_gt import ComponentGt
from gwproto.property_format import SpaceheatName


class PicoBtuMeterComponentGt(ComponentGt):
    Enabled: bool
    FlowMeterType: MakeModel = MakeModel.SAIER__SENHZG1WA
    ConstantGallonsPerTick: float
    SerialNumber: Optional[str] = None
    TypeName: Literal["pico.btu.meter.component.gt"] = "pico.btu.meter.component.gt"
    Version: str = "000"

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

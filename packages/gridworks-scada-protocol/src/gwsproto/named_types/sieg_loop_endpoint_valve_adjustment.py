"""Type sieg.loop.endpoint.valve.adjustment, version 000"""
import time
from typing import Literal

from gwproto.property_format import HandleName, UTCMilliseconds
from pydantic import BaseModel, Field, PositiveInt, StrictInt, model_validator
from typing_extensions import Self

class SiegLoopEndpointValveAdjustment(BaseModel):
    """
    Used to gauarantee that the Siegenthaler valve is fully closed or fully open.
    If the HpKeepPercent is 100% (and matches actual), the SiegLoop actor pushes
    the Siegenthaler valve to "keep more". If 0%, it 
    pushes the valve to "keep less". 
    """ 
    FromHandle: HandleName
    ToHandle: HandleName
    HpKeepPercent: StrictInt
    Seconds: PositiveInt
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["sieg.loop.endpoint.valve.adjustment"] = "sieg.loop.endpoint.valve.adjustment"
    Version: str = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: HpKeepPercent is 0 or 100
        """
        if self.HpKeepPercent not in [0, 100]:
            raise ValueError(f"HpKeepPercent must be 0 or 100, not {self.HpKeepPercent}")
        return self


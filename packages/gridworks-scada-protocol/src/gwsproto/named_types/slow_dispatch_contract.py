from typing import Literal
import time

from pydantic import BaseModel, field_validator, model_validator, PositiveInt, StrictInt
from gwproto.property_format import UUID4Str, UTCSeconds,  LeftRightDotStr
from typing_extensions import Self

class SlowDispatchContract(BaseModel):
    """Represents a dispatch contract between Atn and Scada"""
    ScadaAlias: LeftRightDotStr
    StartS: UTCSeconds
    DurationMinutes: PositiveInt
    AvgPowerWatts:StrictInt
    OilBoilerOn: bool
    ContractId: UUID4Str
    TypeName: Literal["slow.dispatch.contract"] = "slow.dispatch.contract"
    Version: str = "000"

    @field_validator("StartS")
    @classmethod
    def check_start_s(cls, v: int) -> int:
        """
        Axiom 1: StartS should fall on the top of 5 minutes
        """
        if v % 300 != 0:
            raise ValueError(
                f"Axiom 1: SlotStartS should fall on the top of 5 minutes. But got {v % 300} seconds out"
            )
        return v

    @model_validator(mode="after")
    def _check_axiom_1(self) -> Self:
        """OilBoilerOn -> AvgPowerWatts is 0
        """
        if self.OilBoilerOn:
            if self.AvgPowerWatts > 0:
                raise ValueError("OilBoilerOn -> AvgPowerWatts is 0")
        return self

    def contract_end_s(self) -> int:
        return self.StartS + self.DurationMinutes * 60


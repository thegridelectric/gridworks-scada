"""Type energy.instruction, version 000"""

from typing import Literal

from gwproto.property_format import LeftRightDotStr, UTCMilliseconds, UTCSeconds
from pydantic import BaseModel, PositiveInt, StrictInt, field_validator, model_validator
from typing_extensions import Self


class EnergyInstruction(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    SlotStartS: UTCSeconds
    SlotDurationMinutes: PositiveInt
    SendTimeMs: UTCMilliseconds
    AvgPowerWatts: StrictInt
    TypeName: Literal["energy.instruction"] = "energy.instruction"
    Version: Literal["000"] = "000"

    @field_validator("SlotStartS")
    @classmethod
    def check_slot_start_s(cls, v: int) -> int:
        """
        Axiom 1: SlotStartS should fall on the top of 5 minutes
        """
        if v % 300 != 0:
            raise ValueError(
                f"Axiom 1: SlotStartS should fall on the top of 5 minutes. But got {v % 300} seconds out"
            )
        return v

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: SendTime within 10 seconds of SlotStart.
        SendTimeMs should be no more than 10 seconds after SlotStartS
        """
        send_time_s = self.SendTimeMs / 1000
        if send_time_s > self.SlotStartS + 10:
            raise ValueError(
                f"Axiom 2: SendTime within 10 seconds of SlotStart. Got {round(send_time_s - self.SlotStartS, 2)}"
            )
        return self

from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UTCSeconds


class EnergyInstruction(SemaType):
    """Sema: https://schemas.electricity.works/types/energy.instruction/000"""

    from_g_node_alias: LeftRightDot
    slot_start_s: UTCSeconds
    slot_duration_minutes: PositiveInt
    send_time_ms: UTCMilliseconds
    avg_power_watts: StrictInt
    type_name: Literal["energy.instruction"] = "energy.instruction"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "EnergyInstruction":
        """
        Axiom 1: SlotStartOnMinuteBoundary
        SlotStartS SHALL be divisible by 60.
        """
        if self.slot_start_s % 60 != 0:
            raise ValueError("Axiom 1 failed: slot_start_s must be divisible by 60.")
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "EnergyInstruction":
        """
        Axiom 2: SendTimeProximityToSlotStart
        SendTimeMs SHALL be no more than 10 seconds after SlotStartS * 1000.
        """
        if self.send_time_ms > self.slot_start_s * 1000 + 10_000:
            raise ValueError(
                "Axiom 2 failed: send_time_ms must be no more than 10 seconds after slot_start_s."
            )
        return self

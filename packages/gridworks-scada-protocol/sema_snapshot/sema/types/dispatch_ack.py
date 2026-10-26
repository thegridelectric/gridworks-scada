from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class DispatchAck(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.ack/000"""

    from_handle: HandleName
    to_handle: HandleName
    trigger_id: UUID4Str
    unix_time_ms: UTCMilliseconds
    type_name: Literal["gw.dispatch.ack"] = "gw.dispatch.ack"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ToHandleIsBoss
        ToHandle SHALL be the immediate boss of FromHandle (FromHandle with its last
        dot-segment removed).
        """
        boss = ".".join(self.from_handle.split(".")[:-1])
        if boss != self.to_handle:
            raise ValueError(
                f"Axiom 1 violated! ToHandle {self.to_handle} is not the "
                f"immediate boss of FromHandle {self.from_handle}."
            )
        return self

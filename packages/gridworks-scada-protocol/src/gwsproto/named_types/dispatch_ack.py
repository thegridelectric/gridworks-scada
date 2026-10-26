from typing import Literal

from gwsproto.property_format import HandleName, UTCMilliseconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from pydantic import model_validator
from typing_extensions import Self


class DispatchAck(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.ack/000"""

    FromHandle: HandleName
    ToHandle: HandleName
    TriggerId: UUID4Str
    UnixTimeMs: UTCMilliseconds
    TypeName: Literal["gw.dispatch.ack"] = "gw.dispatch.ack"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ToHandleIsBoss.
        ToHandle SHALL be the immediate boss of FromHandle (FromHandle with
        its last dot-segment removed).
        """
        boss = ".".join(self.FromHandle.split(".")[:-1])
        if boss != self.ToHandle:
            raise ValueError(
                f"Axiom 1 (ToHandleIsBoss) failed: ToHandle {self.ToHandle} "
                f"is not the immediate boss of FromHandle {self.FromHandle}"
            )
        return self

from typing import Literal, Optional
from typing_extensions import Self

from pydantic import StrictInt, model_validator

from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    SpaceheatName,
    UTCMilliseconds,
    UUID4Str,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class AnalogDispatch(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/analog.dispatch/000"""

    FromGNodeAlias: Optional[LeftRightDotStr] = None
    FromHandle: HandleName
    ToHandle: HandleName
    AboutName: SpaceheatName
    Value: StrictInt
    TriggerId: UUID4Str
    UnixTimeMs: UTCMilliseconds
    TypeName: Literal["analog.dispatch"] = "analog.dispatch"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: FromHandleIsBoss.
        FromHandle SHALL be the immediate boss of ToHandle (ToHandle with its
        last dot-segment removed), unless ToHandle contains "multiplexer".
        """
        if "multiplexer" in self.ToHandle:
            return self
        if ".".join(self.ToHandle.split(".")[:-1]) != self.FromHandle:
            raise ValueError(
                f"Axiom 1 (FromHandleIsBoss) failed: FromHandle {self.FromHandle} "
                f"is not the immediate boss of ToHandle {self.ToHandle}"
            )
        return self

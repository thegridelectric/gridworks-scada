from typing import Literal, Optional
from typing_extensions import Self

from pydantic import BaseModel, StrictInt, model_validator

from gwsproto.property_format import (
    HandleName,
    LeftRightDotStr,
    SpaceheatName,
    UTCMilliseconds,
    UUID4Str,
)


class AnalogDispatch(BaseModel):
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
        Axiom 1: FromHandle must be the immediate boss of ToHandle, unless ToHandle contains 'multiplexer'.

        """
        if "multiplexer" in self.ToHandle:
            return self
        if ".".join(self.ToHandle.split(".")[:-1]) != self.FromHandle:
            raise ValueError(
                f"FromHandle {self.FromHandle} must be direct boss of ToHandle {self.ToHandle}"
            )
        return self

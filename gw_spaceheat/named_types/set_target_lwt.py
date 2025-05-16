"""Type set.target.lwt, version 000"""
import time
from typing import Literal

from gwproto.property_format import HandleName, UTCMilliseconds
from pydantic import BaseModel, PositiveInt, Field, model_validator
from typing_extensions import Self

class SetTargetLwt(BaseModel):
    FromHandle: HandleName
    ToHandle: HandleName
    TargetLwtF: PositiveInt
    CreatedMs: UTCMilliseconds = Field(default_factory=lambda: int(time.time() * 1000))
    TypeName: Literal["set.target.lwt"] = "set.target.lwt"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: FromHandle is boss of ToHandle
        """
        immediate_boss = ".".join(self.ToHandle.split(".")[:-1])
        if immediate_boss != self.FromHandle:
            raise ValueError(
                f"FromHandle {self.FromHandle} must be immediate boss of ToHandle {self.ToHandle}"
            )
        return self
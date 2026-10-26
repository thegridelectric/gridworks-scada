import time
from typing import Literal
from typing_extensions import Self

from pydantic import PositiveInt, Field, model_validator

from gwsproto.property_format import HandleName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SetTargetLwt(GwsprotoSemaType):
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
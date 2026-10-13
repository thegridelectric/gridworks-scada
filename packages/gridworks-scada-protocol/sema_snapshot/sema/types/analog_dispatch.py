from typing import Literal, Self
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class AnalogDispatch(SemaType):
    """Sema: https://schemas.electricity.works/types/analog.dispatch/000"""

    from_g_node_alias: LeftRightDot | None = None
    from_handle: HandleName
    to_handle: HandleName
    about_name: SpaceheatName
    value: StrictInt
    trigger_id: UUID4Str
    unix_time_ms: UTCMilliseconds
    type_name: Literal["analog.dispatch"] = "analog.dispatch"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: FromHandleIsBoss
        FromHandle SHALL be the immediate boss of ToHandle (ToHandle with its last
        dot-segment removed), unless ToHandle contains "multiplexer".
        """
        if "multiplexer" in self.to_handle:
            return self
        boss = ".".join(self.to_handle.split(".")[:-1])
        if boss != self.from_handle:
            raise ValueError(
                f"Axiom 1 violated! FromHandle {self.from_handle} is not the "
                f"immediate boss of ToHandle {self.to_handle}."
            )
        return self

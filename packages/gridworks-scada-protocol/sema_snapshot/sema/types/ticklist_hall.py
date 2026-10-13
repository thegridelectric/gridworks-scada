from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType


class TicklistHall(SemaType):
    """Sema: https://schemas.electricity.works/types/ticklist.hall/101"""

    hw_uid: str
    first_tick_timestamp_nano_second: StrictInt | None = None
    relative_microsecond_list: list[StrictInt]
    pico_before_post_timestamp_nano_second: StrictInt
    type_name: Literal["ticklist.hall"] = "ticklist.hall"
    version: Literal["101"] = "101"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "TicklistHall":
        """
        Axiom 1: FirstTickTimestampConsistency
        FirstTickTimestampNanoSecond SHALL be absent if and only if RelativeMicrosecondList
        is empty.
        """
        has_timestamp = self.first_tick_timestamp_nano_second is not None
        has_ticks = len(self.relative_microsecond_list) > 0
        if has_timestamp != has_ticks:
            raise ValueError(
                "Axiom 1 failed: first_tick_timestamp_nano_second must be present iff "
                "relative_microsecond_list is non-empty."
            )
        return self

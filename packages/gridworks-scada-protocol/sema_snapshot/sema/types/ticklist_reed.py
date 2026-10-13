from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType


class TicklistReed(SemaType):
    """Sema: https://schemas.electricity.works/types/ticklist.reed/101"""

    hw_uid: str
    first_tick_timestamp_nano_second: StrictInt | None = None
    relative_millisecond_list: list[StrictInt]
    pico_before_post_timestamp_nano_second: StrictInt
    type_name: Literal["ticklist.reed"] = "ticklist.reed"
    version: Literal["101"] = "101"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "TicklistReed":
        """
        Axiom 1: FirstTickTimestampConsistency
        FirstTickTimestampNanoSecond SHALL be absent if and only if RelativeMillisecondList
        is empty.
        """
        has_timestamp = self.first_tick_timestamp_nano_second is not None
        has_ticks = len(self.relative_millisecond_list) > 0
        if has_timestamp != has_ticks:
            raise ValueError(
                "Axiom 1 failed: first_tick_timestamp_nano_second must be present iff "
                "relative_millisecond_list is non-empty."
            )
        return self

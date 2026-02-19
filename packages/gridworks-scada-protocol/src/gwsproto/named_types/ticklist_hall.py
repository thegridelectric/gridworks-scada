"""Type ticklist.hall, version 101"""

from typing import Literal, Optional

from pydantic import BaseModel, StrictInt, model_validator  # Count:true
from typing_extensions import Self


class TicklistHall(BaseModel):
    HwUid: str
    FirstTickTimestampNanoSecond: Optional[StrictInt] = None
    RelativeMicrosecondList: list[StrictInt]
    PicoBeforePostTimestampNanoSecond: StrictInt
    TypeName: Literal["ticklist.hall"] = "ticklist.hall"
    Version: str = "101"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: FirstTickTimestampNanoSecond is none iff RelativeMicrosecondList has length 0.

        """
        if (
            self.FirstTickTimestampNanoSecond is None
            and len(self.RelativeMicrosecondList) > 0
        ):
            raise ValueError(
                "FirstTickTimestampNanoSecond is None but  RelativeMicrosecondList has nonzero length!"
            )
        if self.FirstTickTimestampNanoSecond and len(self.RelativeMicrosecondList) == 0:
            raise ValueError(
                "FirstTickTimestampNanoSecond exists but  RelativeMicrosecondList has no elements!"
            )
        return self

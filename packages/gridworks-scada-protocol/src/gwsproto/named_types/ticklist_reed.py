"""Type ticklist.reed, version 101"""

from typing import Literal, Optional

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class TicklistReed(GwsprotoSemaType):
    HwUid: str
    FirstTickTimestampNanoSecond: Optional[StrictInt] = None
    RelativeMillisecondList: list[StrictInt]
    PicoBeforePostTimestampNanoSecond: StrictInt
    TypeName: Literal["ticklist.reed"] = "ticklist.reed"
    Version: str = "101"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: .
        FirstTickTimestampNanoSecond is None iff RelativeMillisecondList has length 0
        """
        if (
            self.FirstTickTimestampNanoSecond is None
            and len(self.RelativeMillisecondList) > 0
        ):
            raise ValueError(
                "FirstTickTimestampNanoSecond is None but RelativeMillisecondList has nonzero length!"
            )
        if self.FirstTickTimestampNanoSecond and len(self.RelativeMillisecondList) == 0:
            raise ValueError(
                "FirstTickTimestampNanoSecond exists but RelativeMillisecondList has no elements!"
            )
        return self

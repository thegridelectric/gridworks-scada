"""Type ally.gives.up, version 000"""

from typing import Literal

from pydantic import BaseModel


class AllyGivesUp(BaseModel):
    Reason: str  # This allows us to communicate why we're giving up
    TypeName: Literal["ally.gives.up"] = "ally.gives.up"
    Version: Literal["000"] = "000"

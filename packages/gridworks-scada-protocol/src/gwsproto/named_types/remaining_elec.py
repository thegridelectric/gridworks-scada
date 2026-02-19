import uuid
from typing import Literal

from pydantic import BaseModel, Field

from gwsproto.property_format import LeftRightDotStr, UUID4Str


class RemainingElec(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    RemainingWattHours: int
    MessageId: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    TypeName: Literal["remaining.elec"] = "remaining.elec"
    Version: Literal["000"] = "000"

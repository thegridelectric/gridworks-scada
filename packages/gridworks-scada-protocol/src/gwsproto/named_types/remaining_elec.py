import uuid
from typing import Literal

from gwproto.property_format import LeftRightDotStr, UUID4Str
from pydantic import BaseModel, Field


class RemainingElec(BaseModel):
    FromGNodeAlias: LeftRightDotStr
    RemainingWattHours: int
    MessageId: UUID4Str = Field(default_factory=lambda: str(uuid.uuid4()))
    TypeName: Literal["remaining.elec"] = "remaining.elec"
    Version: str = "000"

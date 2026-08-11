from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from gwsproto.property_format import SpaceheatName


class HvacZone(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw1.hvac.zone/000
    """

    Name: SpaceheatName
    Critical: bool
    KwhPerDegF: float
    TempChannelName: Optional[SpaceheatName] = None
    TypeName: Literal["gw1.hvac.zone"] = "gw1.hvac.zone"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

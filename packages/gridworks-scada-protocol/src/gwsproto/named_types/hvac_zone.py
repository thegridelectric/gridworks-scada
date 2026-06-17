from typing import Literal

from pydantic import BaseModel, ConfigDict

from gwsproto.property_format import SpaceheatName


class HvacZone(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw1.hvac.zone/000
    """

    Name: SpaceheatName
    Critical: bool
    KwhPerDegF: float
    TypeName: Literal["gw1.hvac.zone"] = "gw1.hvac.zone"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

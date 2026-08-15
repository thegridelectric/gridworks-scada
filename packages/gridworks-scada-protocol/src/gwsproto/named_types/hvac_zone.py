from typing import Literal, Optional

from pydantic import ConfigDict

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class HvacZone(GwsprotoSemaType):
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

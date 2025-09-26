"""Type baseurl.failure.alert, version 000"""

from typing import Literal

from gwproto.property_format import SpaceheatName
from pydantic import BaseModel


class BaseurlFailureAlert(BaseModel):
    ActorNodeName: SpaceheatName
    HwUid: str
    BaseUrl: str
    Message: str
    TypeName: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    Version: str = "000"

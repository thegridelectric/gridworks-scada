from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import SpaceheatName


class BaseurlFailureAlert(BaseModel):
    ActorNodeName: SpaceheatName
    HwUid: str
    BaseUrl: str
    Message: str
    TypeName: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    Version: Literal["000"] = "000"

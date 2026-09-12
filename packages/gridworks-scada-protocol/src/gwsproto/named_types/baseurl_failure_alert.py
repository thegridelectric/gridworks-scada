from typing import Literal

from pydantic import BaseModel

from gwsproto.property_format import SpaceheatName


class BaseurlFailureAlert(BaseModel):
    """Sema: https://schemas.electricity.works/types/baseurl.failure.alert/100"""

    ActorNodeName: SpaceheatName
    HwUid: str
    BaseUrl: str
    Message: str
    TypeName: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    Version: Literal["100"] = "100"

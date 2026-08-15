from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class BaseurlFailureAlert(GwsprotoSemaType):
    ActorNodeName: SpaceheatName
    HwUid: str
    BaseUrl: str
    Message: str
    TypeName: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    Version: Literal["000"] = "000"

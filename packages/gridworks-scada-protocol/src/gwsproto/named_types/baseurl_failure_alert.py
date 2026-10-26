from typing import Literal

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class BaseurlFailureAlert(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/baseurl.failure.alert/100"""

    ActorNodeName: SpaceheatName
    HwUid: str
    BaseUrl: str
    Message: str
    TypeName: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    Version: Literal["100"] = "100"

from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName


class BaseurlFailureAlert(SemaType):
    """Sema: https://schemas.electricity.works/types/baseurl.failure.alert/100"""

    hw_uid: str
    actor_node_name: SpaceheatName
    base_url: str
    message: str
    type_name: Literal["baseurl.failure.alert"] = "baseurl.failure.alert"
    version: Literal["100"] = "100"

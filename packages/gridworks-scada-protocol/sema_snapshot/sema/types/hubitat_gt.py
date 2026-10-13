from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import MacAddress


class HubitatGt(SemaType):
    """Sema: https://schemas.electricity.works/types/hubitat.gt/000"""

    host: str
    maker_api_id: StrictInt
    access_token: str
    mac_address: MacAddress
    web_listen_enabled: bool
    type_name: Literal["hubitat.gt"] = "hubitat.gt"
    version: Literal["000"] = "000"

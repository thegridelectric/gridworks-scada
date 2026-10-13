from typing import Literal
from sema_snapshot.sema.base import SemaType


class DispatchHold(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.hold/000"""

    operator_hold: bool
    service_contract_broken: bool
    type_name: Literal["gw.dispatch.hold"] = "gw.dispatch.hold"
    version: Literal["000"] = "000"

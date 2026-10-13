from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DispatchHold(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.hold/000"""

    OperatorHold: bool
    ServiceContractBroken: bool
    TypeName: Literal["gw.dispatch.hold"] = "gw.dispatch.hold"
    Version: Literal["000"] = "000"

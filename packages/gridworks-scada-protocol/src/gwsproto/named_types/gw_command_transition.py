from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GwCommandTransition(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.command.transition/000
    """

    Event: str
    ToState: str
    TypeName: Literal["gw.command.transition"] = "gw.command.transition"
    Version: Literal["000"] = "000"

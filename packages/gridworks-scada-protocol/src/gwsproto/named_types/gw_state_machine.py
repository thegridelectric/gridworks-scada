from typing import Literal

from gwsproto.property_format import LeftRightDotStr, SemaVersion, SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class GwStateMachine(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.state.machine/000
    """

    NodeName: SpaceheatName
    StateEnum: LeftRightDotStr
    StateEnumVersion: SemaVersion
    TypeName: Literal["gw.state.machine"] = "gw.state.machine"
    Version: Literal["000"] = "000"

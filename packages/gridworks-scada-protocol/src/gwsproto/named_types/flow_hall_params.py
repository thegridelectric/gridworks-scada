from typing import Literal

from pydantic import PositiveInt

from gwsproto.property_format import (
    SpaceheatName,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FlowHallParams(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flow.hall.params/101"""

    HwUid: str
    ActorNodeName: SpaceheatName
    FlowNodeName: SpaceheatName
    PublishTicklistPeriodS: PositiveInt
    PublishEmptyTicklistAfterS: PositiveInt
    TypeName: Literal["flow.hall.params"] = "flow.hall.params"
    Version: Literal["101"] = "101"

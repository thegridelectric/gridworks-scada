from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import PicoBoardVariant
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class FlowHallParams(SemaType):
    """Sema: https://schemas.electricity.works/types/flow.hall.params/200"""

    hw_uid: str
    actor_node_name: SpaceheatName
    flow_node_name: SpaceheatName
    publish_ticklist_period_s: PositiveInt
    publish_empty_ticklist_after_s: PositiveInt
    pico_board_variant: PicoBoardVariant
    micropython_version: str
    type_name: Literal["flow.hall.params"] = "flow.hall.params"
    version: Literal["200"] = "200"

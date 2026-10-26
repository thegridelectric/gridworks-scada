from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.ticklist_hall import TicklistHall


class TicklistHallReport(SemaType):
    """Sema: https://schemas.electricity.works/types/ticklist.hall.report/000"""

    terminal_asset_alias: LeftRightDot
    channel_name: SpaceheatName
    scada_received_unix_ms: UTCMilliseconds
    ticklist: TicklistHall
    type_name: Literal["ticklist.hall.report"] = "ticklist.hall.report"
    version: Literal["000"] = "000"

from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.types.ticklist_reed import TicklistReed


class TicklistReedReport(SemaType):
    """Sema: https://schemas.electricity.works/types/ticklist.reed.report/000"""

    terminal_asset_alias: LeftRightDot
    channel_name: SpaceheatName
    scada_received_unix_ms: UTCMilliseconds
    ticklist: TicklistReed
    type_name: Literal["ticklist.reed.report"] = "ticklist.reed.report"
    version: Literal["000"] = "000"

from typing import Literal

from gwsproto.named_types.ticklist_hall import TicklistHall
from gwsproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TicklistHallReport(GwsprotoSemaType):
    """
    Used by the SCADA to forward a ticklist.hall message received from a PicoFlowHall module.
    """

    TerminalAssetAlias: LeftRightDotStr
    ChannelName: SpaceheatName
    ScadaReceivedUnixMs: UTCMilliseconds
    Ticklist: TicklistHall
    TypeName: Literal["ticklist.hall.report"] = "ticklist.hall.report"
    Version: Literal["000"] = "000"

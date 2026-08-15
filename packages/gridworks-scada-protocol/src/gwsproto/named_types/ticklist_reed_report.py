from typing import Literal


from gwsproto.named_types.ticklist_reed import TicklistReed
from gwsproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class TicklistReedReport(GwsprotoSemaType):
    """
    Used by the SCADA to forward a ticklist.reed message received from a PicoFlowReed module.
    """

    TerminalAssetAlias: LeftRightDotStr
    ChannelName: SpaceheatName
    ScadaReceivedUnixMs: UTCMilliseconds
    Ticklist: TicklistReed
    TypeName: Literal["ticklist.reed.report"] = "ticklist.reed.report"
    Version: Literal["000"] = "000"

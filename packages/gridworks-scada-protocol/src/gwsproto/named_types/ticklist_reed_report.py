from typing import Literal

from pydantic import BaseModel  # Count:true

from gwsproto.named_types.ticklist_reed import TicklistReed
from gwsproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds


class TicklistReedReport(BaseModel):
    """
    Used by the SCADA to forward a ticklist.reed message received from a PicoFlowReed module.
    """

    TerminalAssetAlias: LeftRightDotStr
    ChannelName: SpaceheatName
    ScadaReceivedUnixMs: UTCMilliseconds
    Ticklist: TicklistReed
    TypeName: Literal["ticklist.reed.report"] = "ticklist.reed.report"
    Version: Literal["000"] = "000"

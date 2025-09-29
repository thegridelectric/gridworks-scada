"""Type async.btu.params, version 000"""

from typing import Literal, Optional

from pydantic import BaseModel, PositiveInt
from gwproto.property_format import (
    SpaceheatName,
)


class AsyncBtuParams(BaseModel):
    """
    Parameters for the GridWorks AsyncBtuMain code
    """

    HwUid: str
    ActorNodeName: SpaceheatName
    FlowChannelName: SpaceheatName
    HotChannelName: SpaceheatName
    ColdChannelName: SpaceheatName
    CtChannelName: Optional[SpaceheatName] = None
    ThermistorBeta: Optional[int] = None
    CapturePeriodS: PositiveInt
    GallonsPerPulse: float
    AsyncCaptureDeltaGpmX100: PositiveInt
    AsyncCaptureDeltaCelsiusX100: PositiveInt
    AsyncCaptureDeltaCtVoltsX100: PositiveInt
    CaptureOffsetS: Optional[float] = None
    TypeName: Literal["async.btu.params"] = "async.btu.params"
    Version: Literal["000"] = "000"

from typing import Literal, Optional
from typing_extensions import Self

from pydantic import BaseModel, PositiveInt, model_validator
from gwsproto.property_format import SpaceheatName


class AsyncBtuParams(BaseModel):
    HwUid: str
    ActorNodeName: SpaceheatName
    FlowChannelName: SpaceheatName
    SendHz: bool
    ReadCtVoltage: bool
    HotChannelName: SpaceheatName
    ColdChannelName: SpaceheatName
    CtChannelName: Optional[SpaceheatName] = None
    ThermistorBeta: Optional[int] = None
    CapturePeriodS: PositiveInt
    GallonsPerPulse: float
    AsyncCaptureDeltaGpmX100: PositiveInt
    AsyncCaptureDeltaCelsiusX100: PositiveInt
    AsyncCaptureDeltaCtVoltsX100: Optional[PositiveInt] = None
    CaptureOffsetS: Optional[float] = None
    TypeName: Literal["async.btu.params"] = "async.btu.params"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ReadCtVoltage is True iff CtChannelName exists
        """
        truthy = [
            bool(self.ReadCtVoltage),
            self.CtChannelName is not None,
        ]
        if not (all(truthy) or not any(truthy)):
            raise ValueError(
                "Axiom 1 violated! ReadCtVoltage and CtChannelName,"
                "must either BOTH be set/present (True/nonnull) or BOTH be unset/absent."
            )
        return self

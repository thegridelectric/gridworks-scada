from pydantic import BaseModel, ConfigDict, PositiveInt, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.enums import Unit
from gwsproto.property_format import (
    SpaceheatName,
)


class ChannelConfig(BaseModel):
    ChannelName: SpaceheatName
    PollPeriodMs: PositiveInt | None = None
    CapturePeriodS: PositiveInt
    AsyncCapture: bool
    AsyncCaptureDelta:  PositiveInt | None = None
    Exponent: StrictInt
    Unit: Unit
    TypeName: str = "channel.config"
    Version: str = "000"

    model_config = ConfigDict(use_enum_values=True)

    def __hash__(self) -> int:
        return hash(self.ChannelName)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Capture and Polling Consistency.
        CapturePeriodMs (CapturePeriodS * 1000) must be larger than PollPeriodMs. If CapturePeriodMs < 10 * PollPeriodMs then CapturePeriodMs must be a multiple of PollPeriodMs.
        """
        # Implement check for axiom 2"
        return self

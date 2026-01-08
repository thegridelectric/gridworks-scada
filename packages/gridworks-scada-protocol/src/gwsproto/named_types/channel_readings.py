from typing import Literal

from pydantic import BaseModel, StrictInt, model_validator  # Count:true
from typing_extensions import Self

from gwsproto.property_format import (
    SpaceheatName,
    UTCMilliseconds,
)


class ChannelReadings(BaseModel):
    """
    A list of timestamped readings (values) for a data channel. This is meant to be reported
    for non-local consumption (AtomicTNode, other) by a SCADA. Therefore, the data channel is
    referenced by its globally unique identifier. The receiver needs to reference this idea
    against a list of the data channels used by the SCADA for accurate parsing.
    """

    ChannelName: SpaceheatName
    ValueList: list[StrictInt]
    ScadaReadTimeUnixMsList: list[UTCMilliseconds]
    TypeName: Literal["channel.readings"] = "channel.readings"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ListLengthConsistency.
        ValueList and ScadaReadTimeUnixMsList must have the same length.
        """
        # Implement check for axiom 1"
        return self

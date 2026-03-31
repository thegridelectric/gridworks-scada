from typing import Literal

from pydantic import BaseModel, StrictInt, model_validator  # Count:true
from typing_extensions import Self

from gwsproto.property_format import (
    SpaceheatName,
    UTCMilliseconds,
)


class ChannelReadings(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/channel-readings/002
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
        len(ValueList) SHALL equal len(ScadaReadTimeUnixMsList).
        """
        if len(self.ValueList) != len(self.ScadaReadTimeUnixMsList):
            raise ValueError(
                "Axiom 1 violated! "
                f"ValueList has length {len(self.ValueList)} but "
                "ScadaReadTimeUnixMsList has length "
                f"{len(self.ScadaReadTimeUnixMsList)}"
            )
        return self

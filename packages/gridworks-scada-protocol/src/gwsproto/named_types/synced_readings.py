from typing import Literal

from pydantic import BaseModel, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import (
    SpaceheatName,
    UTCMilliseconds,
)


class SyncedReadings(BaseModel):
    ChannelNameList: list[SpaceheatName]
    ValueList: list[StrictInt]
    ScadaReadTimeUnixMs: UTCMilliseconds
    TypeName: Literal["synced.readings"] = "synced.readings"
    Version: Literal["000"] = "000"

    def get_value(self, channel_name: str) -> int | None:
        try:
            idx = self.ChannelNameList.index(channel_name)
        except ValueError:
            return None
        return self.ValueList[idx]
    
    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: list Length Consistency.
        len(ChannelNameList) = len(ValueList)
        """
        if len(self.ChannelNameList) != len(self.ValueList):
            raise ValueError("Axiom 1 violated!ChannelNameList and ValueList not the same length")
        return self

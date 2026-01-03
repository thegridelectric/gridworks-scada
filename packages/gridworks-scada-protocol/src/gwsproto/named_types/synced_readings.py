from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator
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

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: list Length Consistency.
        len(ChannelNameList) = len(ValueList)
        """
        # Implement check for axiom 1"
        return self

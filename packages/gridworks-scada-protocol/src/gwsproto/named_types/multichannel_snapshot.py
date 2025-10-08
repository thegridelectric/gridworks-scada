"""Type  multichannel.snapshot, version 000"""

from typing import Literal, Self

from pydantic import BaseModel, StrictInt, ConfigDict, model_validator

from gwproto.property_format import (
    SpaceheatName,
)

class MultichannelSnapshot(BaseModel):
    HwUid: str
    ChannelNameList: list[SpaceheatName]
    MeasurementList: list[StrictInt]
    UnitList: list[str]
    TypeName: Literal["multichannel.snapshot"] = "multichannel.snapshot"

    model_config = ConfigDict(extra='allow')

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: all lists must have the same length
        """
        channel_len = len(self.ChannelNameList)
        measurement_len = len(self.MeasurementList)
        unit_len = len(self.UnitList)
        
        if not (channel_len == measurement_len == unit_len):
            raise ValueError(
                f"All lists must have the same length. Got: "
                f"channel_name_list[{channel_len}], "
                f"measurement_list[{measurement_len}], "
                f"unit_list[{unit_len}]"
            )
        return self


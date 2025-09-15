"""Type channel.flatlined, version 000"""

from typing import Literal

from gwproto.named_types import DataChannelGt
from gwproto.property_format import SpaceheatName
from pydantic import BaseModel, model_validator
from typing_extensions import Self


class ChannelFlatlined(BaseModel):
    FromName: SpaceheatName
    Channel: DataChannelGt
    TypeName: Literal["channel.flatlined"] = "channel.flatlined"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 1:FromName must be Channel.CapturedByNodeName
        """
        if self.Channel.CapturedByNodeName != self.FromName:
            raise ValueError(
                "Axiom 1: FromName must be Channel.CapturedByNodeName"
                f" FromName {self.FromName} != Channel.CapturedByName {self.Channel.CapturedByNodeName}"
            )
        return self

from typing import List, Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.named_types.g_node_gt import GNodeGt


class GwHouse0OperationalParams(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw.house0.operational.params/000"""

    GNodes: List[GNodeGt]
    CaptureTuningList: List[CaptureTuning]
    TypeName: Literal["gw.house0.operational.params"] = "gw.house0.operational.params"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: CaptureTuningChannelUniqueness.
        ChannelName is unique across the CaptureTuningList.
        """
        channel_names = [ct.ChannelName for ct in self.CaptureTuningList]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted(
                {n for n in channel_names if channel_names.count(n) > 1}
            )
            raise ValueError(
                "Axiom 1 (CaptureTuningChannelUniqueness) failed: ChannelName must be "
                f"unique across CaptureTuningList; duplicates: {duplicates}"
            )
        return self

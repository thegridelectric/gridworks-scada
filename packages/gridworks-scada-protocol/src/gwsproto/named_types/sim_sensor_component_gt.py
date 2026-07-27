from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, field_validator

from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.type_helpers.component_base import DeviceComponentBase


class SimSensorComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/sim.sensor.component.gt/000"""

    TypeName: Literal["sim.sensor.component.gt"] = "sim.sensor.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: Sequence[CaptureTuning]) -> Sequence[CaptureTuning]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

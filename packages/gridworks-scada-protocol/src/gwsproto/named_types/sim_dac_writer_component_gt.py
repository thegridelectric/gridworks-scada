from collections.abc import Sequence
from typing import Literal

from pydantic import ConfigDict, field_validator

from gwsproto.named_types.i2c_dac_channel_config import I2cDacChannelConfig
from gwsproto.type_helpers.component_base import DeviceComponentBase


class SimDacWriterComponentGt(DeviceComponentBase):
    """Sema: https://schemas.electricity.works/types/sim.dac.writer.component.gt/000"""

    ConfigList: Sequence[I2cDacChannelConfig]
    TypeName: Literal["sim.dac.writer.component.gt"] = "sim.dac.writer.component.gt"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(
        cls, v: Sequence[I2cDacChannelConfig]
    ) -> Sequence[I2cDacChannelConfig]:
        """Axiom 1: DacChannelUniqueness. DacChannel values are unique in the ConfigList."""
        dac_channels = [config.DacChannel for config in v]
        if len(dac_channels) != len(set(dac_channels)):
            duplicates = sorted({c for c in dac_channels if dac_channels.count(c) > 1})
            raise ValueError(
                f"Axiom 1 violated! DacChannel values must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

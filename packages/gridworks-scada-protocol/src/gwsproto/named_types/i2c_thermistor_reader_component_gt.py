from collections.abc import Sequence
from typing import Literal, Self

from pydantic import model_validator

from gwsproto.enums import TempCalcMethod
from gwsproto.named_types.i2c_thermistor_channel_config import I2cThermistorChannelConfig
from gwsproto.property_format import PascalCase
from gwsproto.type_helpers.component_base import BoardResidentComponentBase


class I2cThermistorReaderComponentGt(BoardResidentComponentBase):
    """
    Sema: https://schemas.electricity.works/types/i2c.thermistor.reader.component.gt/003
    """

    AdcName: PascalCase
    TempCalcMethod: TempCalcMethod
    ConfigList: Sequence[I2cThermistorChannelConfig]

    TypeName: Literal["i2c.thermistor.reader.component.gt"] = "i2c.thermistor.reader.component.gt"
    Version: Literal["003"] = "003"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ChannelNameUniqueness
        Channel names SHALL be unique across the ConfigList.
        """
        channel_names = [config.ChannelName for config in self.ConfigList]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                "Axiom 1 (ChannelNameUniqueness) failed: channel names must be "
                f"unique across the ConfigList; duplicates: {duplicates}"
            )
        return self

from collections import Counter
from collections.abc import Sequence
from typing import Literal, Self
from pydantic import field_validator, model_validator, PositiveFloat

from gwsproto.property_format import SpaceheatName
from gwsproto.named_types.i2c_thermistor_channel_config import I2cThermistorChannelConfig
from gwsproto.type_helpers.component_base import ComponentBase
from gwsproto.enums import TempCalcMethod

class I2cThermistorReaderComponentGt(ComponentBase):
    Bus: SpaceheatName
    AdcAddress: int  # e.g. 0x49
    AdcReferenceVolts: PositiveFloat = 3.3
    SeriesResistanceKOhms: PositiveFloat
    TempCalcMethod: TempCalcMethod
    ConfigList: Sequence[I2cThermistorChannelConfig]

    TypeName: Literal["i2c.thermistor.reader.component.gt"] = "i2c.thermistor.reader.component.gt"
    Version: Literal["002"] = "002"


    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(
        cls, v: Sequence[I2cThermistorChannelConfig]
    ) -> Sequence[I2cThermistorChannelConfig]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ConfigUniqueness.
        - Each ChannelName SHALL appear at most once in ConfigList.
        """
        channel_name_counts = Counter(cfg.ChannelName for cfg in self.ConfigList)
        duplicate_channel_names = [
            channel_name
            for channel_name, count in channel_name_counts.items()
            if count > 1
        ]
        if duplicate_channel_names:
            raise ValueError(
                f"Duplicate ChannelName(s) {sorted(duplicate_channel_names)}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: AddressValidity.
        AdcAddress SHALL be a valid 7-bit I2C address (0–127).
        """
        if not (0 <= self.AdcAddress <= 127):
            raise ValueError(f"Invalid I2C address {self.AdcAddress}")
        return self

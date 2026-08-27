from collections import Counter
from collections.abc import Sequence
from typing import Literal, Self
from pydantic import model_validator, PositiveFloat

from gwsproto.property_format import SpaceheatName
from gwsproto.named_types.i2c_thermistor_channel_config import I2cThermistorChannelConfig
from gwsproto.named_types import ComponentGt
from gwsproto.enums import TempCalcMethod

class I2cThermistorReaderComponentGt(ComponentGt):
    Bus: SpaceheatName
    AdcAddress: int  # e.g. 0x49
    AdcReferenceVolts: PositiveFloat = 3.3
    SeriesResistanceKOhms: PositiveFloat
    TempCalcMethod: TempCalcMethod
    ConfigList: Sequence[I2cThermistorChannelConfig]

    TypeName: Literal["i2c.thermistor.reader.component.gt"] = "i2c.thermistor.reader.component.gt"
    Version: Literal["000"] = "000"


    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: Config uniqueness and device-channel consistency.
        - Each ChannelName SHALL appear at most once in ConfigList.
        - Each AdcChannel SHALL have at most one config whose Unit is Celcius.
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

        celcius_counts_by_adc = Counter(
            cfg.AdcChannel
            for cfg in self.ConfigList
            if cfg.Unit == "Celcius"
        )
        for cfg in self.ConfigList:
            if celcius_counts_by_adc[cfg.AdcChannel] > 1:
                raise ValueError(
                    f"Multiple Celcius configs for AdcChannel {cfg.AdcChannel}"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: Address validity.
        AdcAddress SHALL be a valid 7-bit I2C address (0–127).
        """
        if not (0 <= self.AdcAddress <= 127):
            raise ValueError(f"Invalid I2C address {self.AdcAddress}")
        return self

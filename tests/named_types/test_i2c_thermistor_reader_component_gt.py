"""Tests i2c.thermistor.reader.component.gt type, version 000"""

import pytest

from gwsproto.enums import TempCalcMethod
from gwsproto.named_types import I2cThermistorReaderComponentGt


def base_config(channel_name: str, adc_channel: str) -> dict:
    return {
        "ChannelName": channel_name,
        "AdcChannel": adc_channel,
        "ThermistorBeta": 3977,
        "TypeName": "i2c.thermistor.channel.config",
        "Version": "000",
    }


def base_component() -> dict:
    return {
        "ComponentId": "bd65556c-2ca4-499d-ad25-57767a785685",
        "BoardComponentId": "3f6c1a92-8d4e-4b0a-9c77-21e5b8a4d310",
        "ConfigList": [
            base_config("tank1-depth1-device", "P0"),
            base_config("tank1-depth1-micro-v", "P0"),
        ],
        "AdcName": "Thermistors",
        "DataRateSps": 8,
        "TempCalcMethod": TempCalcMethod.SimpleBeta,
        "TypeName": "i2c.thermistor.reader.component.gt",
        "Version": "000",
    }


def test_i2c_thermistor_reader_component_gt_generated() -> None:
    d = base_component()

    d2 = I2cThermistorReaderComponentGt.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_thermistor_reader_component_gt_channel_name_uniqueness() -> None:
    d = base_component()
    d["ConfigList"][1]["ChannelName"] = "tank1-depth1-device"

    with pytest.raises(ValueError, match="Axiom 1 \\(ChannelNameUniqueness\\) failed"):
        I2cThermistorReaderComponentGt.model_validate(d)

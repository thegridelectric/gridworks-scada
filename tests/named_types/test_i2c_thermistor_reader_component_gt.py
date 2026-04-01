"""Tests i2c.thermistor.reader.component.gt type, version 001"""

import pytest

from gwsproto.enums import TempCalcMethod
from gwsproto.named_types import I2cThermistorReaderComponentGt


def base_config(channel_name: str, adc_channel: str, unit: str) -> dict:
    return {
        "ChannelName": channel_name,
        "CapturePeriodS": 60,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 2000,
        "Exponent": 3 if unit == "Celcius" else 6,
        "Unit": unit,
        "AdcChannel": adc_channel,
        "SendToDerived": False,
        "ThermistorBeta": 3977,
        "TypeName": "i2c.thermistor.channel.config",
        "Version": "001",
    }


def base_component() -> dict:
    return {
        "ComponentId": "bd65556c-2ca4-499d-ad25-57767a785685",
        "ComponentAttributeClassId": "627ac482-24fe-46b2-ba8c-3d6f1e1ee069",
        "ConfigList": [
            base_config("tank1-depth1-device", "P0", "Celcius"),
            base_config("tank1-depth1-micro-v", "P0", "VoltsRms"),
        ],
        "Bus": "primary-scada-i2c",
        "AdcAddress": 73,
        "AdcReferenceVolts": 3.3,
        "SeriesResistanceKOhms": 10.0,
        "TempCalcMethod": TempCalcMethod.SimpleBeta,
        "TypeName": "i2c.thermistor.reader.component.gt",
        "Version": "001",
    }


def test_i2c_thermistor_reader_component_gt_generated() -> None:
    d = base_component()

    d2 = I2cThermistorReaderComponentGt.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_thermistor_reader_component_gt_channel_name_uniqueness() -> None:
    d = base_component()
    d["ConfigList"][1]["ChannelName"] = "tank1-depth1-device"

    with pytest.raises(ValueError, match="Duplicate ChannelName"):
        I2cThermistorReaderComponentGt.model_validate(d)


def test_i2c_thermistor_reader_component_gt_single_celcius_per_adc() -> None:
    d = base_component()
    d["ConfigList"][1]["Unit"] = "Celcius"
    d["ConfigList"][1]["Exponent"] = 3

    with pytest.raises(ValueError, match="Multiple Celcius configs"):
        I2cThermistorReaderComponentGt.model_validate(d)


def test_i2c_thermistor_reader_component_gt_address_validity() -> None:
    d = base_component()
    d["AdcAddress"] = 128

    with pytest.raises(ValueError, match="Invalid I2C address"):
        I2cThermistorReaderComponentGt.model_validate(d)

import pytest

from gwsproto.named_types import (
    AdsChannelConfig,
    DfrConfig,
    ElectricMeterChannelConfig,
    I2cThermistorChannelConfig,
)


def base_channel_fields() -> dict:
    return {
        "ChannelName": "buffer-depth1-device",
        "PollPeriodMs": 200,
        "CapturePeriodS": 300,
        "AsyncCapture": True,
        "AsyncCaptureDelta": 1,
        "Exponent": 0,
        "Unit": "Unitless",
    }


def test_dfr_config_axiom_1() -> None:
    d = {
        **base_channel_fields(),
        "PollPeriodMs": 1000,
        "CapturePeriodS": 1,
        "OutputIdx": 1,
        "InitialVoltsTimes100": 0,
        "TypeName": "dfr.config",
        "Version": "000",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        DfrConfig.model_validate(d)


def test_ads_channel_config_axiom_1() -> None:
    d = {
        **base_channel_fields(),
        "PollPeriodMs": 700,
        "CapturePeriodS": 2,
        "TerminalBlockIdx": 1,
        "ThermistorMakeModel": "EcosensorTempProbe10k",
        "TypeName": "ads.channel.config",
        "Version": "000",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        AdsChannelConfig.model_validate(d)


def test_i2c_thermistor_channel_config_axiom_1() -> None:
    d = {
        **base_channel_fields(),
        "AsyncCaptureDelta": None,
        "AdcChannel": "P1",
        "ThermistorBeta": 3977,
        "TypeName": "i2c.thermistor.channel.config",
        "Version": "001",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        I2cThermistorChannelConfig.model_validate(d)


def test_i2c_thermistor_channel_config_axiom_2() -> None:
    d = {
        **base_channel_fields(),
        "PollPeriodMs": 1000,
        "CapturePeriodS": 1,
        "AdcChannel": "P1",
        "ThermistorBeta": 3977,
        "TypeName": "i2c.thermistor.channel.config",
        "Version": "001",
    }

    with pytest.raises(ValueError, match="Axiom 2 violated!"):
        I2cThermistorChannelConfig.model_validate(d)


def test_electric_meter_channel_config_axiom_1() -> None:
    d = {
        **base_channel_fields(),
        "PollPeriodMs": 700,
        "CapturePeriodS": 2,
        "TypeName": "electric.meter.channel.config",
        "Version": "000",
    }

    with pytest.raises(ValueError, match="Axiom 1 violated!"):
        ElectricMeterChannelConfig.model_validate(d)

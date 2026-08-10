"""Tests i2c.dac.writer.component.gt type, version 000"""

import pytest

from gwsproto.named_types import I2cDacWriterComponentGt


def base_config(dac_channel: str, raw_value: int) -> dict:
    return {
        "DacChannel": dac_channel,
        "PowerOnRawValue": raw_value,
        "PowerOnVref": "Internal",
        "PowerOnGain": 1,
        "TypeName": "i2c.dac.channel.config",
        "Version": "000",
    }


def base_component() -> dict:
    return {
        "ComponentId": "3f6d8a34-5f1e-4c9b-9a37-2e8d41f7c655",
        "BoardComponentId": "9b1c5e2a-77d4-4f6e-8c3a-5f2e9d101b44",
        "DacName": "Dac2",
        "ConfigList": [
            base_config("C", 3020),
            base_config("A", 0),
        ],
        "TypeName": "i2c.dac.writer.component.gt",
        "Version": "000",
    }


def test_i2c_dac_writer_component_gt_generated() -> None:
    d = base_component()

    d2 = I2cDacWriterComponentGt.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_dac_writer_component_gt_dac_channel_uniqueness() -> None:
    d = base_component()
    d["ConfigList"][1]["DacChannel"] = "C"

    with pytest.raises(ValueError, match="Axiom 1 \\(DacChannelUniqueness\\) failed"):
        I2cDacWriterComponentGt.model_validate(d)


def test_i2c_dac_channel_config_eeprom_ranges() -> None:
    d = base_component()
    d["ConfigList"][0]["PowerOnRawValue"] = 4096

    with pytest.raises(ValueError, match="Axiom 1 \\(EepromRanges\\) failed"):
        I2cDacWriterComponentGt.model_validate(d)

"""Tests i2c.dac.output.component.gt type, version 000, and its
dac.output.config."""

import pytest

from gwsproto.named_types import I2cDacOutputComponentGt


def base_config(dac_channel: str, raw_value: int) -> dict:
    return {
        "ChannelName": "secondary-010v",
        "ActorName": "secondary-010v",
        "DacChannel": dac_channel,
        "PowerOnRawValue": raw_value,
        "PowerOnVref": "Internal",
        "PowerOnGain": 1,
        "TypeName": "dac.output.config",
        "Version": "000",
    }


def base_component() -> dict:
    return {
        "ComponentId": "3f6d8a34-5f1e-4c9b-9a37-2e8d41f7c655",
        "BoardComponentId": "9b1c5e2a-77d4-4f6e-8c3a-5f2e9d101b44",
        "DacName": "Dac2",
        "ConfigList": [base_config("C", 3020)],
        "TypeName": "i2c.dac.output.component.gt",
        "Version": "000",
    }


def test_i2c_dac_output_component_gt_generated() -> None:
    d = base_component()
    d2 = I2cDacOutputComponentGt.model_validate(d).model_dump(exclude_none=True)
    assert d2 == d


def test_i2c_dac_output_component_gt_axiom_1() -> None:
    d = base_component()
    d["ConfigList"].append(base_config("A", 0))
    with pytest.raises(ValueError, match="Axiom 1 \\(ExactlyOneConfig\\) failed"):
        I2cDacOutputComponentGt.model_validate(d)
    d["ConfigList"] = []
    with pytest.raises(ValueError, match="Axiom 1 \\(ExactlyOneConfig\\) failed"):
        I2cDacOutputComponentGt.model_validate(d)


def test_dac_output_config_axiom_1() -> None:
    d = base_component()
    d["ConfigList"][0]["PowerOnRawValue"] = 4096
    with pytest.raises(ValueError, match="Axiom 1 \\(EepromRanges\\) failed"):
        I2cDacOutputComponentGt.model_validate(d)
    d = base_component()
    d["ConfigList"][0]["PowerOnGain"] = 3
    with pytest.raises(ValueError, match="Axiom 1 \\(EepromRanges\\) failed"):
        I2cDacOutputComponentGt.model_validate(d)

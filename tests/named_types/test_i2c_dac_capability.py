"""Tests i2c.dac.capability type, version 000"""

import pytest

from gwsproto.named_types import I2cDacCapability


def base_capability() -> dict:
    return {
        "DacName": "Dac2",
        "I2cBus": "DefaultBus",
        "I2cAddress": 96,
        "MuxName": "DacMux",
        "MuxChannel": 2,
        "DacType": "Mcp4728",
        "Channels": 4,
        "TypeName": "i2c.dac.capability",
        "Version": "000",
    }


def test_i2c_dac_capability_generated() -> None:
    d = base_capability()

    d2 = I2cDacCapability.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_dac_capability_mux_pairing() -> None:
    d = base_capability()
    del d["MuxChannel"]

    with pytest.raises(ValueError, match="Axiom 1 \\(MuxPairing\\) failed"):
        I2cDacCapability.model_validate(d)

"""Tests i2c.ct.interface.capability type, version 000"""

from gwsproto.named_types import I2cCtInterfaceCapability
from tests.named_types.sema_oracle import assert_refused


def base_capability() -> dict:
    return {
        "Name": "Ct",
        "I2cBus": "DefaultBus",
        "I2cAddress": 72,
        "AdcType": "Ads1115",
        "AdcReferenceVolts": 3.3,
        "Channels": 4,
        "MuxName": "DacMux",
        "MuxChannel": 4,
        "TypeName": "i2c.ct.interface.capability",
        "Version": "000",
    }


def test_i2c_ct_interface_capability_generated() -> None:
    d = base_capability()

    d2 = I2cCtInterfaceCapability.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_i2c_ct_interface_capability_axiom_1_mux_pairing() -> None:
    d = base_capability()
    del d["MuxChannel"]

    assert_refused(I2cCtInterfaceCapability, d, match="Axiom 1 \\(MuxPairing\\) failed")

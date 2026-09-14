"""Tests tank.module.params type, version 200"""

import pytest
from pydantic import ValidationError

from gwsproto.enums import PicoBoardVariant
from gwsproto.named_types import TankModuleParams

WIRE_200 = {
    "HwUid": "pico_1a2b3c",
    "ActorNodeName": "tank1",
    "PicoAB": "a",
    "CapturePeriodS": 60,
    "Samples": 1000,
    "NumSampleAverages": 10,
    "AsyncCaptureDeltaMicroVolts": 2000,
    "PicoBoardVariant": "PicoRaspberryWifi2040",
    "MicropythonVersion": "1.24.1",
    "TypeName": "tank.module.params",
    "Version": "200",
}


def test_tank_module_params_generated() -> None:
    d2 = TankModuleParams.model_validate(WIRE_200).model_dump(exclude_none=True)

    assert d2 == WIRE_200


def test_tank_module_params_axiom_1() -> None:
    d = dict(WIRE_200, PicoAB="c")
    with pytest.raises(ValidationError, match="Axiom 1"):
        TankModuleParams.model_validate(d)


def test_unknown_board_coerces_to_unknown() -> None:
    d = dict(WIRE_200, PicoBoardVariant="Esp32Something")
    assert (
        TankModuleParams.model_validate(d).PicoBoardVariant == PicoBoardVariant.Unknown
    )


def test_version_110_wire_shape_is_rejected() -> None:
    """The scada accepts 200 only; a pico still on 110 firmware is rejected."""
    d = {
        k: v
        for k, v in WIRE_200.items()
        if k not in ("PicoBoardVariant", "MicropythonVersion")
    }
    d["Version"] = "110"
    with pytest.raises(ValidationError):
        TankModuleParams.model_validate(d)

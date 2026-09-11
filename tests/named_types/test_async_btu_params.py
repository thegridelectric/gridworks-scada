"""Tests async.btu.params type, version 100"""

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from gwsproto.enums import PicoBoardVariant
from gwsproto.named_types import AsyncBtuParams

WIRE_100 = {
    "HwUid": "pico_3a202a",
    "ActorNodeName": "primary-btu",
    "FlowChannelName": "primary-flow",
    "SendHz": False,
    "ReadCtVoltage": False,
    "HotChannelName": "hp-lwt",
    "ColdChannelName": "hp-ewt",
    "CapturePeriodS": 60,
    "GallonsPerPulse": 0.0009,
    "AsyncCaptureDeltaGpmX100": 10,
    "AsyncCaptureDeltaCelsiusX100": 20,
    "AsyncCaptureDeltaCtVoltsX100": 20,
    "PicoBoardVariant": "PicoRaspberryWifi2040",
    "MicropythonVersion": "1.24.1",
    "TypeName": "async.btu.params",
    "Version": "100",
}


def test_async_btu_params_generated() -> None:
    d2 = AsyncBtuParams.model_validate(WIRE_100).model_dump(exclude_none=True)

    assert d2 == WIRE_100


def test_async_btu_params_axiom_1() -> None:
    d = dict(WIRE_100, ReadCtVoltage=True)
    with pytest.raises(ValidationError, match="Axiom 1"):
        AsyncBtuParams.model_validate(d)


def test_unknown_board_coerces_to_unknown() -> None:
    d = dict(WIRE_100, PicoBoardVariant="Esp32Something")
    assert (
        AsyncBtuParams.model_validate(d).PicoBoardVariant == PicoBoardVariant.Unknown
    )


def test_version_000_wire_shape_is_rejected() -> None:
    """The scada accepts 100 only; a pico still on 000 firmware is rejected."""
    d = {
        k: v
        for k, v in WIRE_100.items()
        if k not in ("PicoBoardVariant", "MicropythonVersion")
    }
    d["Version"] = "000"
    with pytest.raises(ValidationError):
        AsyncBtuParams.model_validate(d)


def test_conforms_to_sema_runtime(tmp_path) -> None:
    payload = tmp_path / "async_btu_params.json"
    payload.write_text(json.dumps(WIRE_100))
    result = subprocess.run(
        [sys.executable, "-m", "sema", "validate", str(payload)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "No module named sema" in result.stderr:
        pytest.skip("sema runtime not importable in this venv")
    assert result.returncode == 0, result.stdout + result.stderr

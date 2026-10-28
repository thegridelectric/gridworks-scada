"""A tank pico's asynchronous trigger is authored once, on its depths'
temperature channels: the assembly step refuses a micro-volt tuning that
states a delta, a temperature channel without one, or depths that disagree."""

import json
from pathlib import Path

import pytest

from sema_to_dc import SEMA_LAYOUT_BY_TYPENAME, check_tank_capture_deltas, decode_operational_params

CONFIG = Path(__file__).parent.parent / "config"
PAIRS = [
    ("gw.house0.orange.layout.json", "gw.house0.orange.operational.params.json"),
    ("gw.nolan.layout.json", "gw.nolan.operational.params.json"),
]


def pair(layout: str, ops: str) -> tuple:
    static = json.loads((CONFIG / layout).read_text())
    return SEMA_LAYOUT_BY_TYPENAME[static["TypeName"]].model_validate(static), json.loads(
        (CONFIG / ops).read_text()
    )


def tuning(ops: dict, channel: str) -> dict:
    return next(t for t in ops["CaptureTuningList"] if t["ChannelName"] == channel)


@pytest.mark.parametrize("layout, ops", PAIRS)
def test_fixture_pairs_pass(layout: str, ops: str) -> None:
    word, ops_d = pair(layout, ops)
    check_tank_capture_deltas(word, decode_operational_params(ops_d))


@pytest.mark.parametrize("layout, ops", PAIRS)
def test_micro_volt_delta_refused(layout: str, ops: str) -> None:
    word, ops_d = pair(layout, ops)
    tuning(ops_d, "tank1-depth2-micro-v")["AsyncCaptureDelta"] = 2000
    with pytest.raises(ValueError, match="tank1-depth2-micro-v.*states an AsyncCaptureDelta"):
        check_tank_capture_deltas(word, decode_operational_params(ops_d))


@pytest.mark.parametrize("layout, ops", PAIRS)
def test_temperature_delta_missing_refused(layout: str, ops: str) -> None:
    word, ops_d = pair(layout, ops)
    del tuning(ops_d, "tank1-depth3-device")["AsyncCaptureDelta"]
    with pytest.raises(ValueError, match="tank1-depth3-device.*state no AsyncCaptureDelta"):
        check_tank_capture_deltas(word, decode_operational_params(ops_d))


@pytest.mark.parametrize("layout, ops", PAIRS)
def test_depths_disagreeing_refused(layout: str, ops: str) -> None:
    word, ops_d = pair(layout, ops)
    tuning(ops_d, "tank1-depth1-device")["AsyncCaptureDelta"] += 1
    with pytest.raises(ValueError, match="tank1's temperature channels state different deltas"):
        check_tank_capture_deltas(word, decode_operational_params(ops_d))


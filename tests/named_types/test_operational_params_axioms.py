"""Rejecting tests for the operational-params axioms (on a fixture of each
family), the tariff's window axiom, and zero.ten.power.on: each mutates a
valid fixture into one violation."""

import json
from pathlib import Path

import pytest

from gwsproto.named_types import OperationalParams, TouTariff, ZeroTenPowerOn

CONFIG = Path(__file__).parent.parent / "config"

OPS_FIXTURES = [
    "gw.house0.orange.operational.params.json",
    "gw.nolan.operational.params.json",
]


def ops(name: str) -> dict:
    return json.loads((CONFIG / name).read_text())


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_1_duplicate_channel(name: str) -> None:
    d = ops(name)
    d["CaptureTuningList"].append(dict(d["CaptureTuningList"][0]))
    with pytest.raises(ValueError, match="Axiom 1 \\(CaptureTuningChannelUniqueness\\)"):
        OperationalParams.model_validate(d)


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_2_duplicate_node(name: str) -> None:
    d = ops(name)
    d["ZeroTenPowerOnList"].append(dict(d["ZeroTenPowerOnList"][0]))
    with pytest.raises(ValueError, match="Axiom 2 \\(ZeroTenPowerOnNodeUniqueness\\)"):
        OperationalParams.model_validate(d)


def test_gw_operational_params_family_block_is_discriminated() -> None:
    d = ops("gw.nolan.operational.params.json")
    d["FamilyParams"]["TypeName"] = "gw.house0.family.params"
    with pytest.raises(ValueError, match="SiegLoopStrategy"):
        OperationalParams.model_validate(d)


def test_gw_tou_tariff_axiom_1_overlapping_windows() -> None:
    d = ops("gw.house0.orange.operational.params.json")["Tariff"]
    d["OnPeakWindows"] = [
        {"Start": "07:00", "End": "12:00", "Days": ["Monday"],
         "TypeName": "gw.tou.window", "Version": "000"},
        {"Start": "11:00", "End": "13:00", "Days": ["Monday"],
         "TypeName": "gw.tou.window", "Version": "000"},
    ]
    with pytest.raises(ValueError, match="Axiom 1 \\(PerDayWindowNonOverlap\\)"):
        TouTariff.model_validate(d)


def test_zero_ten_power_on_axiom_1_above_ten_volts() -> None:
    with pytest.raises(ValueError, match="Axiom 1 \\(TenVoltCeiling\\)"):
        ZeroTenPowerOn(NodeName="dist-010v", PowerOnVoltsTimesTen=101)

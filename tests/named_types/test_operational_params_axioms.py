"""Rejecting tests for the operational-params axioms (both family words) and
for zero.ten.power.on: each mutates a valid fixture into one violation."""

import json
from pathlib import Path

import pytest

from gwsproto.named_types import (
    House0OperationalParams,
    NolanOperationalParams,
    ZeroTenPowerOn,
)

CONFIG = Path(__file__).parent.parent / "config"


def house0_ops() -> dict:
    return json.loads((CONFIG / "gw.house0.operational.params.json").read_text())


def nolan_ops() -> dict:
    return json.loads((CONFIG / "gw.nolan.operational.params.json").read_text())


def duplicate_power_on(d: dict) -> dict:
    d["ZeroTenPowerOnList"].append(dict(d["ZeroTenPowerOnList"][0]))
    return d


def overlapping_windows(d: dict) -> dict:
    d["OnPeakWindows"] = [
        {"Start": "07:00", "End": "12:00", "Days": ["Monday"],
         "TypeName": "gw.tou.window", "Version": "000"},
        {"Start": "11:00", "End": "13:00", "Days": ["Monday"],
         "TypeName": "gw.tou.window", "Version": "000"},
    ]
    return d


def test_gw_house0_operational_params_axiom_2_duplicate_node() -> None:
    with pytest.raises(ValueError, match="Axiom 2 \\(ZeroTenPowerOnNodeUniqueness\\)"):
        House0OperationalParams.model_validate(duplicate_power_on(house0_ops()))


def test_gw_house0_operational_params_axiom_3_overlapping_windows() -> None:
    with pytest.raises(ValueError, match="Axiom 3 \\(PerDayWindowNonOverlap\\)"):
        House0OperationalParams.model_validate(overlapping_windows(house0_ops()))


def test_gw_nolan_operational_params_axiom_2_duplicate_node() -> None:
    with pytest.raises(ValueError, match="Axiom 2 \\(ZeroTenPowerOnNodeUniqueness\\)"):
        NolanOperationalParams.model_validate(duplicate_power_on(nolan_ops()))


def test_gw_nolan_operational_params_axiom_3_overlapping_windows() -> None:
    with pytest.raises(ValueError, match="Axiom 3 \\(PerDayWindowNonOverlap\\)"):
        NolanOperationalParams.model_validate(overlapping_windows(nolan_ops()))


def test_zero_ten_power_on_axiom_1_above_ten_volts() -> None:
    with pytest.raises(ValueError, match="Axiom 1 \\(TenVoltCeiling\\)"):
        ZeroTenPowerOn(NodeName="dist-010v", PowerOnVoltsTimesTen=101)

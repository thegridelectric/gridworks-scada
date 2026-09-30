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


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_3_standby_accepts_dispatch(name: str) -> None:
    d = ops(name)
    d["Standby"] = True
    with pytest.raises(ValueError, match="Axiom 3 \\(StandbyRefusesDispatch\\)"):
        OperationalParams.model_validate(d)


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_3_standby_refuses_for_another_reason(name: str) -> None:
    d = ops(name)
    d["Standby"] = True
    d["AcceptsDispatch"] = False
    d["DispatchRefusalReason"] = "NoAggregator"
    with pytest.raises(ValueError, match="Axiom 3 \\(StandbyRefusesDispatch\\)"):
        OperationalParams.model_validate(d)


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_4_refusal_without_reason(name: str) -> None:
    d = ops(name)
    d["AcceptsDispatch"] = False
    with pytest.raises(ValueError, match="Axiom 4 \\(RefusalReasonPresence\\)"):
        OperationalParams.model_validate(d)


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_4_reason_while_accepting(name: str) -> None:
    d = ops(name)
    d["DispatchRefusalReason"] = "NoAggregator"
    with pytest.raises(ValueError, match="Axiom 4 \\(RefusalReasonPresence\\)"):
        OperationalParams.model_validate(d)


@pytest.mark.parametrize("name", OPS_FIXTURES)
def test_gw_operational_params_axiom_5_a_monitor_only_energizes_nothing(name: str) -> None:
    d = ops(name)
    d["StandbyPosture"] = "MonitorOnly"
    d["EnergizedStandbyRelays"] = ["hp-failsafe-relay"]
    with pytest.raises(ValueError, match="Axiom 5 \\(PostureRelaysPerFamily\\)"):
        OperationalParams.model_validate(d)


def test_gw_operational_params_axiom_5_b_house0_list_is_fixed() -> None:
    d = ops("gw.house0.orange.operational.params.json")
    assert d["EnergizedStandbyRelays"] == ["hp-failsafe-relay", "aquastat-ctrl-relay"]
    for relays in ([], ["hp-failsafe-relay"], ["hp-failsafe-relay", "aquastat-ctrl-relay", "store-pump-relay"]):
        d["EnergizedStandbyRelays"] = relays
        with pytest.raises(ValueError, match="Axiom 5 \\(PostureRelaysPerFamily\\)"):
            OperationalParams.model_validate(d)


def test_gw_operational_params_axiom_5_c_nolan_list_is_empty() -> None:
    d = ops("gw.nolan.operational.params.json")
    assert d["EnergizedStandbyRelays"] == []
    d["EnergizedStandbyRelays"] = ["iso-valve-relay"]
    with pytest.raises(ValueError, match="Axiom 5 \\(PostureRelaysPerFamily\\)"):
        OperationalParams.model_validate(d)


def test_standby_relays_are_relays_the_normal_node_claims() -> None:
    """Assembly refuses an EnergizedStandbyRelays name that is not a Relay
    ShNode whose boot handle sits directly under the tree root (the relays
    local control's normal node claims): a relay under a command node, a
    non-relay node, and an unknown name each fail."""
    from sema_to_dc import check_energized_standby_relays, decode_operational_params

    layout = json.loads((CONFIG / "gw.house0.orange.layout.json").read_text())
    d = ops("gw.house0.orange.operational.params.json")
    d["StandbyPosture"] = "MonitorOnly"
    d["EnergizedStandbyRelays"] = []
    check_energized_standby_relays(decode_operational_params(d), layout)
    for bad in ("hp-scada-ops-relay", "hp-loop-on-off-relay", "vdc-relay", "hp-boss", "no-such-relay"):
        d["StandbyPosture"] = "NoHeatingOrCooling"
        d["EnergizedStandbyRelays"] = ["hp-failsafe-relay", "aquastat-ctrl-relay"]
        good = decode_operational_params(d)
        bad_ops = good.model_copy(update={"EnergizedStandbyRelays": [bad]})
        with pytest.raises(ValueError, match=f"EnergizedStandbyRelays.*{bad}"):
            check_energized_standby_relays(bad_ops, layout)

"""Tests heating.curve type, version 000"""

from gwsproto.named_types import HeatingCurve
from tests.named_types.sema_oracle import assert_refused


def curve() -> dict:
    return {
        "BaselineAlphaTimes10": 55,
        "BaselineBetaTimes100": -10,
        "BaselineGammaEx6": 0,
        "AlphaEx6": -490027,
        "BetaEx6": 26201,
        "GammaEx6": -892,
        "DeltaEx6": -570,
        "EpsilonEx6": 5847,
        "ZetaEx6": 293782,
        "EtaEx6": 535515,
        "RhoTimes100": 131,
        "IntermediatePowerKw": 1.5,
        "IntermediateRswtF": 100,
        "DdPowerKw": 5.5,
        "DdRswtF": 150,
        "DdRoomTempF": 65,
        "DdDeltaTF": 20,
        "MaxEwtF": 170,
        "MassFlowKgH": 426,
        "TypeName": "heating.curve",
        "Version": "000",
    }


def test_heating_curve_generated() -> None:
    d = curve()
    assert HeatingCurve.model_validate(d).model_dump(exclude_none=True) == d


def test_heating_curve_rho_is_positive() -> None:
    assert_refused(HeatingCurve, {**curve(), "RhoTimes100": 0}, match="RhoTimes100")


def test_heating_curve_axiom_1_design_day_rswt_below_intermediate() -> None:
    assert_refused(
        HeatingCurve, {**curve(), "DdRswtF": 99, "IntermediateRswtF": 100}, match="Axiom 1"
    )


def test_heating_curve_axiom_2_design_day_power_below_intermediate() -> None:
    assert_refused(
        HeatingCurve, {**curve(), "DdPowerKw": 1.4, "IntermediatePowerKw": 1.5}, match="Axiom 2"
    )

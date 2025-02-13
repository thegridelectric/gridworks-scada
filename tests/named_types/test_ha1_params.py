"""Tests ha1.params type, version 000"""

from named_types import Ha1Params


def test_ha1_params_generated() -> None:
    d = {
        "AlphaTimes10": 120,
        "BetaTimes100": -22,
        "GammaEx6": 0,
        "IntermediatePowerKw": 1.5,
        "IntermediateRswtF": 100,
        "DdPowerKw": 12,
        "DdRswtF": 160,
        "DdDeltaTF": 20,
        "HpMaxKwTh": 6,
        "MaxEwtF": 170,
        "LoadOverestimationPercent": 10,
        "StratBossDist010": 100,
        "TypeName": "ha1.params",
        "Version": "003",
    }

    d2 = Ha1Params.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d

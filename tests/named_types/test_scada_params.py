"""Tests scada.params type, version 001"""

from named_types import ScadaParams


def test_scada_params_generated() -> None:
    d = {
        "FromGNodeAlias": "d1.isone.rose",
        "FromName": "a",
        "ToName": "h",
        "UnixTimeMs": 1731637846788,
        "MessageId": "37b64437-f5b2-4a80-b5fc-3d5a9f6b5b59",
        "NewParams": {
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
            "Version": "002",
        },
        "TypeName": "scada.params",
        "Version": "002",
    }

    d2 = ScadaParams.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d

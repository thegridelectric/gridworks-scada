"""flo.params 000: the twin agrees with the snapshot on the word's example
and refuses each axiom's violation."""

import copy
import json
from pathlib import Path

from gwsproto.named_types import FloParams
from tests.named_types.sema_oracle import assert_conforms, assert_refused

CONFIG = Path(__file__).parent.parent / "config"

PREVIOUS_PATH = {
    "StartUnixS": 1762005600,
    "StepDurationMinutes": [60, 60, 60],
    "HpAvgWList": [4200, 0, 3100],
    "StoreWhList": [38500, 31200, 36800],
    "TypeName": "flo.optimal.path",
    "Version": "000",
}

EXAMPLE = {
    "GNodeAlias": "hw1.isone.me.versant.keene.oak",
    "CreatedMs": 1762008900000,
    "StartUnixS": 1762009200,
    "StepDurationMinutes": [60, 60, 60],
    "LmpUsdMwhList": [28.14, 28.53, 46.38],
    "DistUsdMwhList": [50.13, 50.13, 487.63],
    "OatFList": [30.0, 29.0, 28.5],
    "LoadKwhList": [3.5, 3.6, 3.8],
    "RswtFList": [120.0, 121.0, 122.5],
    "WeatherForecastId": "5f1c2b3a-8d4e-4f60-9a7b-1c2d3e4f5a6b",
    "SeasonalStorageMode": "BufferOnly",
    "TanksModeled": 1,
    "GallonsPerTank": 120,
    "TempSensorsPerTank": 3,
    "MaxTankTempF": 170.0,
    "InitialTopTempF": 120.0,
    "InitialMiddleTempF": 110.0,
    "InitialBottomTempF": 100.0,
    "InitialThermocline1": 1,
    "InitialThermocline2": 2,
    "HpCurrentlyOn": False,
    "HpMaxKwEl": 9.66,
    "HpTurnOnMinutes": 12,
    "CopIntercept": 1.5,
    "CopOatCoeff": 0.015,
    "CopLwtCoeff": 0.0,
    "CopMin": 1.5,
    "CopMinOatF": 0.0,
    "PriceMaxUsdMwh": 2000.0,
    "PriceMinUsdMwh": -100.0,
    "TypeName": "flo.params",
    "Version": "000",
}


def bruce_tuning() -> dict:
    ops = json.loads((CONFIG / "gw.house0.orange.operational.params.json").read_text())
    return ops["FloTuning"]


def example() -> dict:
    d = copy.deepcopy(EXAMPLE)
    d["Tuning"] = bruce_tuning()
    return d


def test_example_conforms() -> None:
    assert_conforms(FloParams.model_validate(example()))


def test_alice_tuning_conforms() -> None:
    d = example()
    d["Tuning"] = {"TypeName": "flo.tuning.alice", "Version": "000"}
    assert_conforms(FloParams.model_validate(d))


def test_previous_run_pair_conforms() -> None:
    d = example()
    d["PreviousOptimalPath"] = copy.deepcopy(PREVIOUS_PATH)
    d["PreviousEstimateElecUsdMwhNow"] = 78.27
    assert_conforms(FloParams.model_validate(d))


def test_flo_params_axiom_1_step_list_lengths() -> None:
    d = example()
    d["OatFList"] = [30.0, 29.0]
    assert_refused(FloParams, d, match="Axiom 1 \\(StepListLengths\\)")


def test_flo_params_axiom_2_thermoclines_within_the_store() -> None:
    d = example()
    d["InitialThermocline2"] = 4
    assert_refused(FloParams, d, match="Axiom 2 \\(ThermoclinesWithinTheStore\\)")


def test_flo_params_axiom_3_buffer_is_one_tank() -> None:
    d = example()
    d["TanksModeled"] = 3
    d["InitialThermocline2"] = 2
    assert_refused(FloParams, d, match="Axiom 3 \\(BufferIsOneTank\\)")


def test_flo_params_axiom_4_price_bounds() -> None:
    d = example()
    d["PriceMinUsdMwh"] = 2000.0
    assert_refused(FloParams, d, match="Axiom 4 \\(PriceBounds\\)")


def test_flo_params_axiom_5_previous_run_together() -> None:
    d = example()
    d["PreviousOptimalPath"] = copy.deepcopy(PREVIOUS_PATH)
    assert_refused(FloParams, d, match="Axiom 5 \\(PreviousRunTogether\\)")

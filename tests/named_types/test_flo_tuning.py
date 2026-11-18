"""Rejecting tests for the flo.tuning.bruce axioms: each mutates the fleet
tuning in an ops fixture into one violation."""

import json
from pathlib import Path

from gwsproto.named_types import FloTuningBruce
from tests.named_types.sema_oracle import assert_refused

CONFIG = Path(__file__).parent.parent / "config"


def bruce() -> dict:
    ops = json.loads((CONFIG / "gw.house0.orange.operational.params.json").read_text())
    return ops["FloTuning"]


def test_flo_tuning_bruce_axiom_1_one_line_per_bucket() -> None:
    d = bruce()
    d["LoadBucketUpperKwhList"] = [10.0]
    assert_refused(FloTuningBruce, d, match="Axiom 1 \\(OneLinePerBucket\\)")


def test_flo_tuning_bruce_axiom_2_buckets_ascend() -> None:
    d = bruce()
    d["LoadBucketUpperKwhList"] = [10.0, 5.0]
    d["RwtInterceptByBucketList"] = [49.0, 49.0, 49.0]
    d["RwtSlopeByBucketList"] = [0.4, 0.4, 0.4]
    assert_refused(FloTuningBruce, d, match="Axiom 2 \\(BucketsAscend\\)")


def test_flo_tuning_bruce_accepts_the_fleet_tuning() -> None:
    FloTuningBruce.model_validate(bruce())


def test_a_001_tuning_in_operational_params_loads_with_the_penalty_off() -> None:
    from sema_to_dc import decode_operational_params

    d = json.loads((CONFIG / "gw.house0.orange.operational.params.json").read_text())
    tuning = dict(d["FloTuning"])
    del tuning["UnmetLoadPenaltyEnabled"]
    del tuning["UnmetLoadPenaltyWeight"]
    tuning["Version"] = "001"
    d["FloTuning"] = tuning
    word = decode_operational_params(d)
    assert d["FloTuning"]["Version"] == "001"
    assert "UnmetLoadPenaltyEnabled" not in d["FloTuning"]
    assert word.FloTuning.Version == "002"
    assert word.FloTuning.UnmetLoadPenaltyEnabled is False
    assert word.FloTuning.UnmetLoadPenaltyWeight == 10.0


def test_a_002_tuning_in_operational_params_keeps_its_penalty() -> None:
    from sema_to_dc import decode_operational_params

    d = json.loads((CONFIG / "gw.house0.orange.operational.params.json").read_text())
    word = decode_operational_params(d)
    assert word.FloTuning.Version == "002"
    assert word.FloTuning.UnmetLoadPenaltyEnabled is True
    assert word.FloTuning.UnmetLoadPenaltyWeight == 10.0

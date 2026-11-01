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

"""flo.optimal.path 000: the twin agrees with the snapshot on the word's
example and refuses each axiom's violation."""

import copy

from gwsproto.named_types import FloOptimalPath
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "StartUnixS": 1762009200,
    "StepDurationMinutes": [60, 60, 60],
    "HpAvgWList": [4200, 0, 3100],
    "StoreWhList": [38500, 31200, 36800],
    "TypeName": "flo.optimal.path",
    "Version": "000",
}


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(FloOptimalPath.model_validate(example()))


def test_flo_optimal_path_axiom_1_step_list_lengths() -> None:
    d = example()
    d["StoreWhList"] = [38500, 31200]
    assert_refused(FloOptimalPath, d, match="Axiom 1 \\(StepListLengths\\)")

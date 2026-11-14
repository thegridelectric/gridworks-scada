"""flo.path.penalties.bruce 000: the twin agrees with the snapshot on the
word's example and refuses each axiom's violation."""

import copy

from gwsproto.named_types import FloPathPenaltiesBruce
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "RswtPenaltyUsdList": [0.0, 0.0, 0.42],
    "StabilityPenaltyUsdList": [0.0, 0.15, 0.0],
    "ShortCyclePenaltyUsdList": [0.0, 0.0, 0.0],
    "TerminalCostUsd": 1.87,
    "TerminalCostEmptyStoreUsd": 5.6,
    "PathCostUsd": 8.3,
    "TypeName": "flo.path.penalties.bruce",
    "Version": "000",
}


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(FloPathPenaltiesBruce.model_validate(example()))


def test_flo_path_penalties_bruce_axiom_1_penalty_list_lengths() -> None:
    d = example()
    d["ShortCyclePenaltyUsdList"] = [0.0, 0.0]
    assert_refused(FloPathPenaltiesBruce, d, match="Axiom 1 \\(PenaltyListLengths\\)")


def test_flo_path_penalties_bruce_axiom_2_terminal_cost_bound() -> None:
    d = example()
    d["TerminalCostUsd"] = d["TerminalCostEmptyStoreUsd"] + 0.01
    assert_refused(FloPathPenaltiesBruce, d, match="Axiom 2 \\(TerminalCostBound\\)")

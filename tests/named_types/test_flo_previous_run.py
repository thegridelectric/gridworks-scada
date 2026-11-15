"""flo.previous.run 000: the twin agrees with the snapshot on the word's
example and refuses its axiom's violation."""

import copy

from gwsproto.named_types import FloPreviousRun
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "Path": {
        "StartUnixS": 1762009200,
        "StepDurationMinutes": [60, 60, 60],
        "HpAvgWList": [4200, 0, 3100],
        "StoreWhList": [38500, 31200, 36800],
        "TypeName": "flo.optimal.path",
        "Version": "000",
    },
    "ClearedPairIndex": 1,
    "ClearedPair": {
        "PriceX1000": 150000,
        "QuantityX1000": 4200,
        "TypeName": "price.quantity.unitless",
        "Version": "001",
    },
    "PriceUnit": "USDPerMWh",
    "QuantityUnit": "AvgkW",
    "NextSlotPriceX1000": 142500,
    "CreatedMs": 1762009260000,
    "TypeName": "flo.previous.run",
    "Version": "000",
}


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(FloPreviousRun.model_validate(example()))


def test_avg_mw_quantity_scales_to_watts() -> None:
    d = example()
    d["QuantityUnit"] = "AvgMW"
    d["ClearedPair"]["QuantityX1000"] = 4
    d["Path"]["HpAvgWList"][0] = 4000
    assert_conforms(FloPreviousRun.model_validate(d))


def test_flo_previous_run_axiom_1_path_starts_at_the_bid() -> None:
    d = example()
    d["Path"]["HpAvgWList"][0] = 5000
    assert_refused(FloPreviousRun, d, match="Axiom 1 \\(PathStartsAtTheBid\\)")

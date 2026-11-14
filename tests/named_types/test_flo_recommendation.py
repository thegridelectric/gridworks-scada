"""flo.recommendation 001: the twin agrees with the snapshot on the word's
example and refuses each axiom's violation."""

import copy

from gwsproto.named_types import FloRecommendation
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def pair(price_x1000: int, quantity_x1000: int) -> dict:
    return {
        "PriceX1000": price_x1000,
        "QuantityX1000": quantity_x1000,
        "TypeName": "price.quantity.unitless",
        "Version": "001",
    }


def path(hp_avg_w_list: list[int], start_unix_s: int = 1762009200) -> dict:
    return {
        "StartUnixS": start_unix_s,
        "StepDurationMinutes": [60, 60, 60],
        "HpAvgWList": hp_avg_w_list,
        "StoreWhList": [38500, 31200, 36800],
        "TypeName": "flo.optimal.path",
        "Version": "000",
    }


def store_state() -> dict:
    return {
        "StoreLayers": 12,
        "TopFList": [160, 158, 160],
        "MiddleFList": [130, 128, 131],
        "BottomFList": [100, 100, 101],
        "Thermocline1List": [8, 6, 8],
        "Thermocline2List": [11, 9, 10],
        "EmptyStoreWh": 20000,
        "FullStoreWh": 45000,
        "TypeName": "flo.tank.store.path",
        "Version": "000",
    }


def penalties() -> dict:
    return {
        "RswtPenaltyUsdList": [0.0, 0.31, 0.0],
        "StabilityPenaltyUsdList": [0.0, 0.0, 0.0],
        "ShortCyclePenaltyUsdList": [0.0, 0.0, 0.0],
        "TerminalCostUsd": 2.14,
        "TerminalCostEmptyStoreUsd": 5.6,
        "PathCostUsd": 9.1,
        "TypeName": "flo.path.penalties.bruce",
        "Version": "000",
    }


EXAMPLE = {
    "BidderAlias": "hw1.isone.me.versant.keene.oak",
    "PqPairs": [pair(2000000, 0), pair(150000, 4200)],
    "PriceUnit": "USDPerMWh",
    "QuantityUnit": "AvgkW",
    "OptimalPathList": [path([0, 0, 3100]), path([4200, 0, 3100])],
    "FloName": "bruce",
    "FloRepo": "github.com/thdfw/optimal-flexibility",
    "FloGitCommit": "2711f59a0b1c2d3e4f5061728394a5b6c7d8e9f0",
    "CreatedMs": 1762008900000,
    "TypeName": "flo.recommendation",
    "Version": "001",
}


def annotated() -> dict:
    """The example with a store state and a penalties word per path."""
    d = example()
    d["StoreStateList"] = [store_state(), store_state()]
    d["PathPenaltiesList"] = [penalties(), penalties()]
    return d


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(FloRecommendation.model_validate(example()))


def test_annotated_example_conforms() -> None:
    assert_conforms(FloRecommendation.model_validate(annotated()))


def test_alice_answer_one_pair_zero_quantity_conforms() -> None:
    d = example()
    d["PqPairs"] = [pair(2000000, 0)]
    d["OptimalPathList"] = [path([0, 0, 0])]
    assert_conforms(FloRecommendation.model_validate(d))


def test_flo_recommendation_axiom_1_at_least_one_pair() -> None:
    d = example()
    d["PqPairs"] = []
    d["OptimalPathList"] = []
    assert_refused(FloRecommendation, d, match="Axiom 1 \\(AtLeastOnePair\\)")


def test_flo_recommendation_axiom_2_path_per_pair() -> None:
    d = example()
    d["OptimalPathList"] = d["OptimalPathList"][:1]
    assert_refused(FloRecommendation, d, match="Axiom 2 \\(PathPerPair\\)")


def test_flo_recommendation_axiom_3_first_step_is_the_bid() -> None:
    d = example()
    d["OptimalPathList"][1]["HpAvgWList"][0] = 5000
    assert_refused(FloRecommendation, d, match="Axiom 3 \\(FirstStepIsTheBid\\)")


def test_avg_mw_quantity_scales_to_watts() -> None:
    d = example()
    d["QuantityUnit"] = "AvgMW"
    d["PqPairs"][1]["QuantityX1000"] = 4
    d["OptimalPathList"][1]["HpAvgWList"][0] = 4000
    assert_conforms(FloRecommendation.model_validate(d))


def test_flo_recommendation_axiom_4_a_prices_strictly_decrease() -> None:
    d = example()
    d["PqPairs"][1]["PriceX1000"] = 2000000
    assert_refused(FloRecommendation, d, match="Axiom 4 \\(PairsDescend\\) clause a")


def test_flo_recommendation_axiom_4_b_quantities_do_not_decrease() -> None:
    d = example()
    d["PqPairs"][0]["QuantityX1000"] = 5000
    d["OptimalPathList"][0]["HpAvgWList"][0] = 5000
    assert_refused(FloRecommendation, d, match="Axiom 4 \\(PairsDescend\\) clause b")


def test_flo_recommendation_axiom_5_paths_start_together() -> None:
    d = example()
    d["OptimalPathList"][1]["StartUnixS"] = 1762012800
    assert_refused(FloRecommendation, d, match="Axiom 5 \\(PathsStartTogether\\)")


def test_flo_recommendation_axiom_6_store_state_per_path() -> None:
    d = annotated()
    d["StoreStateList"] = d["StoreStateList"][:1]
    assert_refused(FloRecommendation, d, match="Axiom 6 \\(StoreStatePerPath\\)")


def test_flo_recommendation_axiom_6_store_state_has_the_paths_steps() -> None:
    d = annotated()
    for key in ("TopFList", "MiddleFList", "BottomFList", "Thermocline1List", "Thermocline2List"):
        d["StoreStateList"][1][key] = d["StoreStateList"][1][key][:2]
    assert_refused(FloRecommendation, d, match="Axiom 6 \\(StoreStatePerPath\\)")


def test_flo_recommendation_axiom_7_penalties_per_path() -> None:
    d = annotated()
    d["PathPenaltiesList"] = d["PathPenaltiesList"][:1]
    assert_refused(FloRecommendation, d, match="Axiom 7 \\(PenaltiesPerPath\\)")


def test_flo_recommendation_axiom_7_penalties_have_the_paths_steps() -> None:
    d = annotated()
    for key in ("RswtPenaltyUsdList", "StabilityPenaltyUsdList", "ShortCyclePenaltyUsdList"):
        d["PathPenaltiesList"][0][key] = d["PathPenaltiesList"][0][key][:2]
    assert_refused(FloRecommendation, d, match="Axiom 7 \\(PenaltiesPerPath\\)")

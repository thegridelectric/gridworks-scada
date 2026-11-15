"""flo.tank.store.path 000: the twin agrees with the snapshot on the word's
example and refuses each axiom's violation."""

import copy

from gwsproto.named_types import FloTankStorePath
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
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


def example() -> dict:
    return copy.deepcopy(EXAMPLE)


def test_example_conforms() -> None:
    assert_conforms(FloTankStorePath.model_validate(example()))


def test_a_two_band_store_sets_both_thermoclines_equal() -> None:
    d = example()
    d["Thermocline2List"] = d["Thermocline1List"]
    assert_conforms(FloTankStorePath.model_validate(d))


def test_flo_tank_store_path_axiom_1_step_list_lengths() -> None:
    d = example()
    d["BottomFList"] = [100, 100]
    assert_refused(FloTankStorePath, d, match="Axiom 1 \\(StepListLengths\\)")


def test_flo_tank_store_path_axiom_2_thermoclines_ordered() -> None:
    d = example()
    d["Thermocline1List"][1] = 10
    assert_refused(FloTankStorePath, d, match="Axiom 2 \\(ThermoclinesWithinTheStore\\)")


def test_flo_tank_store_path_axiom_2_thermoclines_within_the_store() -> None:
    d = example()
    d["Thermocline2List"][2] = 13
    assert_refused(FloTankStorePath, d, match="Axiom 2 \\(ThermoclinesWithinTheStore\\)")


def test_flo_tank_store_path_axiom_3_empty_below_full() -> None:
    d = example()
    d["EmptyStoreWh"] = d["FullStoreWh"]
    assert_refused(FloTankStorePath, d, match="Axiom 3 \\(EmptyBelowFull\\)")

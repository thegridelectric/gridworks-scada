"""The shared store temperature pass (`actors/hydronic/store_temps.py`),
as a pure function: scrub the implausible, fill the missing from below,
baseline from the cold pipe or the coldest reporting layer, never a
constant."""

from actors.hydronic.store_temps import (
    MAX_VALID_TANK_TEMP_F,
    MIN_VALID_TANK_TEMP_F,
    scrub_and_fill_store_temps,
)

LAYERS = ["tank1-depth1", "tank1-depth2", "tank1-depth3", "tank2-depth1", "tank2-depth2", "tank2-depth3"]
COLD_PIPE = "store-cold-pipe"


def run(temps: dict[str, float]) -> dict[str, float]:
    scrub_and_fill_store_temps(temps, LAYERS, COLD_PIPE)
    return temps


def test_bounds_are_the_edges_of_water_in_a_tank() -> None:
    assert (MIN_VALID_TANK_TEMP_F, MAX_VALID_TANK_TEMP_F) == (35, 200)


def test_complete_and_plausible_is_untouched() -> None:
    temps = {layer: 150.0 - i for i, layer in enumerate(LAYERS)}
    assert run(dict(temps)) == temps


def test_missing_layers_take_the_layer_below() -> None:
    temps = run({"tank1-depth3": 140.0, "tank2-depth2": 120.0, "tank2-depth3": 110.0})
    assert temps["tank1-depth1"] == temps["tank1-depth2"] == 140.0
    assert temps["tank2-depth1"] == 120.0


def test_bottom_missing_layer_takes_the_cold_pipe() -> None:
    temps = run({"tank1-depth1": 150.0, COLD_PIPE: 100.0})
    assert temps["tank2-depth3"] == 100.0
    assert temps["tank1-depth2"] == 100.0  # everything under the top fills from the pipe


def test_bottom_missing_layer_takes_the_coldest_layer_without_a_cold_pipe() -> None:
    temps = run({"tank1-depth1": 150.0, "tank2-depth1": 120.0})
    assert temps["tank2-depth3"] == 120.0
    assert temps["tank1-depth3"] == 120.0


def test_implausible_readings_are_dropped_then_filled() -> None:
    temps = run({"tank1-depth1": 250.0, "tank1-depth2": 140.0, "tank1-depth3": 20.0,
                 "tank2-depth1": 130.0, "tank2-depth2": 125.0, "tank2-depth3": 120.0})
    assert temps["tank1-depth1"] == 140.0
    assert temps["tank1-depth3"] == 130.0


def test_an_implausible_cold_pipe_is_ignored() -> None:
    temps = run({"tank1-depth1": 150.0, COLD_PIPE: -40.0})
    assert temps["tank2-depth3"] == 150.0
    assert temps[COLD_PIPE] == -40.0  # not a store layer: left to its own reader


def test_no_valid_reading_fills_nothing() -> None:
    assert run({"tank1-depth1": 300.0}) == {}
    assert run({COLD_PIPE: 100.0}) == {COLD_PIPE: 100.0}

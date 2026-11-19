"""The plant flux word decodes its own shape and holds its lists to one length."""

from gwsproto.named_types import SimPlantFlux
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def flux() -> dict:
    return {
        "ChannelNameList": ["hp-odu-pwr", "buffer-depth1"],
        "ValueList": [3215, 48500],
        "ScadaReadTimeUnixMs": 1735689600123,
        "ActualTimeUtc": "2026-06-12T13:20:00.000Z",
        "TypeName": "sim.plant.flux",
        "Version": "000",
    }


def test_sim_plant_flux_round_trip() -> None:
    d = flux()
    word = SimPlantFlux.model_validate(d)
    assert word.model_dump(by_alias=True, exclude_none=True) == d
    assert_conforms(word)


def test_sim_plant_flux_axiom_1_list_lengths_differ() -> None:
    d = flux()
    d["ValueList"] = [3215]
    assert_refused(SimPlantFlux, d, match="Axiom 1")


def test_sim_plant_flux_refuses_a_non_integer_value() -> None:
    d = flux()
    d["ValueList"] = [3215, 48.5]
    assert_refused(SimPlantFlux, d)


def test_sim_plant_flux_refuses_a_wall_time_without_millis() -> None:
    d = flux()
    d["ActualTimeUtc"] = "2026-06-12T13:20:00Z"
    assert_refused(SimPlantFlux, d)

"""The plant actuation word decodes its own shape for each pin action."""

import pytest

from gwsproto.enums import ChangeRelayPin
from gwsproto.named_types import SimPlantActuation
from tests.named_types.sema_oracle import assert_conforms, assert_refused


def actuation() -> dict:
    return {
        "RelayName": "hp-scada-ops-relay",
        "Action": "Energize",
        "ActuationTimeUnixMs": 1735689600123,
        "ActualTimeUtc": "2026-06-12T13:20:00.000Z",
        "TypeName": "sim.plant.actuation",
        "Version": "000",
    }


@pytest.mark.parametrize("action", list(ChangeRelayPin))
def test_sim_plant_actuation_round_trip(action: ChangeRelayPin) -> None:
    d = actuation()
    d["Action"] = action.value
    word = SimPlantActuation.model_validate(d)
    assert word.Action is action
    assert word.model_dump(by_alias=True, exclude_none=True, mode="json") == d
    assert_conforms(word)


def test_sim_plant_actuation_refuses_a_malformed_relay_name() -> None:
    d = actuation()
    d["RelayName"] = "Hp Scada Ops Relay"
    assert_refused(SimPlantActuation, d)

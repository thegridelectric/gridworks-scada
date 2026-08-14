"""Tests relay.actor.config type, version 003"""

import pytest

from gwsproto.named_types import RelayActorConfig


def base_config() -> dict:
    return {
        "ChannelName": "hp-scada-ops-relay-state",
        "RelayIdx": 6,
        "ActorName": "relay6",
        "WiringConfig": "NormallyClosed",
        "EventType": "change.relay.state",
        "DeEnergizingEvent": "CloseRelay",
        "EnergizingEvent": "OpenRelay",
        "StateType": "relay.closed.or.open",
        "DeEnergizedState": "RelayClosed",
        "EnergizedState": "RelayOpen",
        "TypeName": "relay.actor.config",
        "Version": "003",
    }


def test_relay_actor_config_generated() -> None:
    d = base_config()

    d2 = RelayActorConfig.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d


def test_relay_actor_config_axiom_1() -> None:
    d = base_config()
    d["EnergizingEvent"] = "NotARealRelayEvent"

    with pytest.raises(ValueError, match="Axiom 1 \\(RelayEventEnumConsistency\\) failed"):
        RelayActorConfig.model_validate(d)


def test_relay_actor_config_axiom_2() -> None:
    d = base_config()
    d["EnergizedState"] = "NotARealRelayState"

    with pytest.raises(ValueError, match="Axiom 2 \\(RelayStateEnumConsistency\\) failed"):
        RelayActorConfig.model_validate(d)


def test_relay_actor_config_axiom_3() -> None:
    d = base_config()
    d["EnergizedState"] = "RelayClosed"

    with pytest.raises(ValueError, match="Axiom 3 \\(RelayEventStateMatch\\) failed"):
        RelayActorConfig.model_validate(d)

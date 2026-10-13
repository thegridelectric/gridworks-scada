"""Tests relay.actor.config type, version 003"""


from gwsproto.named_types import RelayActorConfig
from tests.named_types.sema_oracle import assert_refused


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

    assert_refused(RelayActorConfig, d, match="Axiom 1 \\(RelayEventEnumConsistency\\) failed")


def test_relay_actor_config_axiom_2() -> None:
    d = base_config()
    d["EnergizedState"] = "NotARealRelayState"

    assert_refused(RelayActorConfig, d, match="Axiom 2 \\(RelayStateEnumConsistency\\) failed")


def test_relay_actor_config_axiom_3() -> None:
    d = base_config()
    d["EnergizedState"] = "RelayClosed"

    assert_refused(RelayActorConfig, d, match="Axiom 3 \\(RelayEventStateMatch\\) failed")

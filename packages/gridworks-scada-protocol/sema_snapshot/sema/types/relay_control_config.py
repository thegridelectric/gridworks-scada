from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ChangeRelayState
from sema_snapshot.sema.enums import RelayClosedOrOpen
from sema_snapshot.sema.enums import RelayWiringConfig
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import SpaceheatName


class RelayControlConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/relay.control.config/000"""

    channel_name: SpaceheatName
    actor_name: SpaceheatName
    wiring_config: RelayWiringConfig
    event_type: LeftRightDot
    de_energizing_event: NonEmptyString
    energizing_event: NonEmptyString
    state_type: LeftRightDot
    de_energized_state: NonEmptyString
    energized_state: NonEmptyString
    type_name: Literal["relay.control.config"] = "relay.control.config"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "RelayControlConfig":
        """
        Axiom 1: RelayEventEnumConsistency
        If EventType equals "change.relay.state", then DeEnergizingEvent and EnergizingEvent
        SHALL both be valid values of change.relay.state:000.
        """
        if self.event_type == "change.relay.state":
            valid = set(ChangeRelayState.values())
            if (
                self.de_energizing_event not in valid
                or self.energizing_event not in valid
            ):
                raise ValueError(
                    "Axiom 1 failed: relay state events must be valid change.relay.state values."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "RelayControlConfig":
        """
        Axiom 2: RelayStateEnumConsistency
        If StateType equals "relay.closed.or.open", then DeEnergizedState and EnergizedState
        SHALL both be valid values of relay.closed.or.open:000.
        """
        if self.state_type == "relay.closed.or.open":
            valid = set(RelayClosedOrOpen.values())
            if (
                self.de_energized_state not in valid
                or self.energized_state not in valid
            ):
                raise ValueError(
                    "Axiom 2 failed: relay states must be valid relay.closed.or.open values."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "RelayControlConfig":
        """
        Axiom 3: RelayEventStateMatch
        If EventType equals "change.relay.state" and StateType equals
        "relay.closed.or.open", then:

          - DeEnergizingEvent "CloseRelay" SHALL imply DeEnergizedState "RelayClosed"
          - DeEnergizingEvent "OpenRelay" SHALL imply DeEnergizedState "RelayOpen"
          - EnergizingEvent "CloseRelay" SHALL imply EnergizedState "RelayClosed"
          - EnergizingEvent "OpenRelay" SHALL imply EnergizedState "RelayOpen"
        """
        if (
            self.state_type != "relay.closed.or.open"
            or self.event_type != "change.relay.state"
        ):
            return self

        event_to_state = {
            "CloseRelay": "RelayClosed",
            "OpenRelay": "RelayOpen",
        }
        if event_to_state.get(self.de_energizing_event) != self.de_energized_state:
            raise ValueError(
                "Axiom 3 failed: de_energizing_event is inconsistent with de_energized_state."
            )
        if event_to_state.get(self.energizing_event) != self.energized_state:
            raise ValueError(
                "Axiom 3 failed: energizing_event is inconsistent with energized_state."
            )
        return self

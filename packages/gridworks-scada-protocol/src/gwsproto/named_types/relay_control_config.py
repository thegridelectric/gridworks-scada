from typing import Literal

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from gwsproto.enums import ChangeRelayState, RelayClosedOrOpen, RelayWiringConfig
from gwsproto.property_format import LeftRightDotStr, SpaceheatName


class RelayControlConfig(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/relay.control.config/000
    """

    ChannelName: SpaceheatName
    ActorName: SpaceheatName
    WiringConfig: RelayWiringConfig
    EventType: LeftRightDotStr
    DeEnergizingEvent: str
    EnergizingEvent: str
    StateType: LeftRightDotStr
    DeEnergizedState: str
    EnergizedState: str
    TypeName: Literal["relay.control.config"] = "relay.control.config"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: RelayEventEnumConsistency.
        If EventType equals "change.relay.state", then DeEnergizingEvent and
        EnergizingEvent SHALL both be valid values of change.relay.state:000.
        """
        if self.EventType == "change.relay.state":
            valid = set(ChangeRelayState.values())
            if self.DeEnergizingEvent not in valid or self.EnergizingEvent not in valid:
                raise ValueError(
                    "Axiom 1 (RelayEventEnumConsistency) failed: relay state "
                    "events must be valid change.relay.state values."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: RelayStateEnumConsistency.
        If StateType equals "relay.closed.or.open", then DeEnergizedState and
        EnergizedState SHALL both be valid values of relay.closed.or.open:000.
        """
        if self.StateType == "relay.closed.or.open":
            valid = set(RelayClosedOrOpen.values())
            if self.DeEnergizedState not in valid or self.EnergizedState not in valid:
                raise ValueError(
                    "Axiom 2 (RelayStateEnumConsistency) failed: relay states "
                    "must be valid relay.closed.or.open values."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: RelayEventStateMatch.
        If EventType equals "change.relay.state" and StateType equals
        "relay.closed.or.open": DeEnergizingEvent "CloseRelay" implies
        DeEnergizedState "RelayClosed", "OpenRelay" implies "RelayOpen",
        and likewise for the energizing pair.
        """
        if (
            self.EventType != "change.relay.state"
            or self.StateType != "relay.closed.or.open"
        ):
            return self
        event_to_state = {"CloseRelay": "RelayClosed", "OpenRelay": "RelayOpen"}
        if event_to_state.get(self.DeEnergizingEvent) != self.DeEnergizedState:
            raise ValueError(
                "Axiom 3 (RelayEventStateMatch) failed: DeEnergizingEvent is "
                "inconsistent with DeEnergizedState."
            )
        if event_to_state.get(self.EnergizingEvent) != self.EnergizedState:
            raise ValueError(
                "Axiom 3 (RelayEventStateMatch) failed: EnergizingEvent is "
                "inconsistent with EnergizedState."
            )
        return self

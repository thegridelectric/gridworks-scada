from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import RelayWiringConfig, RelayClosedOrOpen, ChangeRelayState
from gwsproto.named_types import ChannelConfig
from gwsproto.property_format import (
    SpaceheatName, LeftRightDotStr
)


class RelayActorConfig(ChannelConfig):
    """
    Sema: https://schemas.electricity.works/types/relay.actor.config/002
    """

    RelayIdx: PositiveInt
    ActorName: SpaceheatName
    WiringConfig: RelayWiringConfig
    EventType: LeftRightDotStr
    DeEnergizingEvent: str
    EnergizingEvent: str
    StateType: LeftRightDotStr
    DeEnergizedState: str
    EnergizedState: str
    TypeName: Literal["relay.actor.config"] = "relay.actor.config"
    Version: Literal["002"] = "002"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: EventType, DeEnergizingEvent/EnergizingEvent consistency.
        If the event type is the name of a known enum, then the DeEnergizingEvent, EnergizingEvent pair are the values of that enum.
        """
        # Implement check for axiom 1"
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: StateType, EnergizedState/DeEnergizedState consistency.
        If the state type is the name of a known enum, then the DeEnergizedState, EnergizedState pair are the values of that enum.
        """
        # Implement check for axiom 2"
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: Events and States match. .
         E.g. if RelayOpen is the EnergizedState then the EnergizingEvent is OpenRelay.
        """
        # Implement check for axiom 3"
        return self


    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: ClosedOpenWiringConsistency

        If:
        - StateType == "relay.closed.or.open"
        - EventType == "change.relay.state"

        then WiringConfig determines the required mapping:
        - NormallyClosed:
            DeEnergizedState = "RelayClosed"
            DeEnergizingEvent = "CloseRelay"
            EnergizedState   = "RelayOpen"
            EnergizingEvent  = "OpenRelay"

        - NormallyOpen:
            DeEnergizedState = "RelayOpen"
            DeEnergizingEvent = "OpenRelay"
            EnergizedState   = "RelayClosed"
            EnergizingEvent  = "CloseRelay"
        """
        if (
            self.StateType == "relay.closed.or.open"
            and self.EventType == "change.relay.state"
        ):
            if self.WiringConfig == RelayWiringConfig.NormallyClosed:
                if self.DeEnergizedState !=  RelayClosedOrOpen.RelayClosed:
                    raise ValueError(
                        "For NormallyClosed wiring, DeEnergizedState must be 'RelayClosed'."
                    )
                if self.DeEnergizingEvent != ChangeRelayState.CloseRelay:
                    raise ValueError(
                        "For NormallyClosed wiring, DeEnergizingEvent must be 'CloseRelay'."
                    )
                if self.EnergizedState != RelayClosedOrOpen.RelayOpen:
                    raise ValueError(
                        "For NormallyClosed wiring, EnergizedState must be 'RelayOpen'."
                    )
                if self.EnergizingEvent != ChangeRelayState.OpenRelay:
                    raise ValueError(
                        "For NormallyClosed wiring, EnergizingEvent must be 'OpenRelay'."
                    )

            elif self.WiringConfig == RelayWiringConfig.NormallyOpen:
                if self.DeEnergizedState != RelayClosedOrOpen.RelayOpen:
                    raise ValueError(
                        "For NormallyOpen wiring, DeEnergizedState must be 'RelayOpen'."
                    )
                if self.DeEnergizingEvent != ChangeRelayState.OpenRelay:
                    raise ValueError(
                        "For NormallyOpen wiring, DeEnergizingEvent must be 'OpenRelay'."
                    )
                if self.EnergizedState != RelayClosedOrOpen.RelayClosed:
                    raise ValueError(
                        "For NormallyOpen wiring, EnergizedState must be 'RelayClosed'."
                    )
                if self.EnergizingEvent != ChangeRelayState.CloseRelay:
                    raise ValueError(
                        "For NormallyOpen wiring, EnergizingEvent must be 'CloseRelay'."
                    )

        return self
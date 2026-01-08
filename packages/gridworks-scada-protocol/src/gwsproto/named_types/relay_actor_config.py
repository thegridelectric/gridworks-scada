from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import RelayWiringConfig
from gwsproto.named_types import ChannelConfig
from gwsproto.property_format import (
    SpaceheatName,
)


class RelayActorConfig(ChannelConfig):
    """
    Relay Actor Config.

    Used to associate individual relays on a multi-channel relay board to specific SpaceheatNode
    actors. Each actor managed by the Spaceheat SCADA has an associated SpaceheatNode. That
    Node will be associated to a relay board component with multiple relays. Th relay board
    will have a list of relay actor configs so that the actor can identify which relay it has
    purview over. Has DeEnergizedState and EnergizedState

    [More info](https://gridworks-protocol.readthedocs.io/en/latest/spaceheat-actor.html)
    """

    RelayIdx: PositiveInt
    ActorName: SpaceheatName
    WiringConfig: RelayWiringConfig
    EventType: str
    DeEnergizingEvent: str
    EnergizingEvent: str
    StateType: str
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

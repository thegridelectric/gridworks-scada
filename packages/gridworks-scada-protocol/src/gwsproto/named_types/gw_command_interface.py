from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import (
    ChangeRelayState,
    FiveVBossState,
    HpBossState,
    PicoCyclerState,
    RebootPicos,
    RelayClosedOrOpen,
    Turn5VOnOff,
    TurnHpOnOff,
)
from gwsproto.named_types.gw_command_transition import GwCommandTransition
from gwsproto.property_format import LeftRightDotStr, SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType

EVENT_VOCABULARY: dict[str, set[str]] = {
    ChangeRelayState.enum_name(): set(ChangeRelayState.values()),
    TurnHpOnOff.enum_name(): set(TurnHpOnOff.values()),
    RebootPicos.enum_name(): set(RebootPicos.values()),
    Turn5VOnOff.enum_name(): set(Turn5VOnOff.values()),
}

STATE_VOCABULARY: dict[str, set[str]] = {
    RelayClosedOrOpen.enum_name(): set(RelayClosedOrOpen.values()),
    HpBossState.enum_name(): set(HpBossState.values()),
    PicoCyclerState.enum_name(): set(PicoCyclerState.values()),
    FiveVBossState.enum_name(): set(FiveVBossState.values()),
}


class GwCommandInterface(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.command.interface/000
    """

    ActorName: SpaceheatName
    EventType: LeftRightDotStr
    StateType: LeftRightDotStr
    Commands: List[GwCommandTransition]
    TypeName: Literal["gw.command.interface"] = "gw.command.interface"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NonEmptyCommands.
        Commands SHALL be non-empty.
        """
        if not self.Commands:
            raise ValueError(
                f"Axiom 1 (NonEmptyCommands) failed: {self.ActorName} has no commands!"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: EventsAreVocabulary.
        If EventType equals "change.relay.state", "turn.hp.on.off" or
        "reboot.picos", every Commands entry's Event SHALL be a value of
        change.relay.state:000, turn.hp.on.off:000 or reboot.picos:000
        respectively.
        """
        valid = EVENT_VOCABULARY.get(self.EventType)
        if valid is not None:
            for command in self.Commands:
                if command.Event not in valid:
                    raise ValueError(
                        f"Axiom 2 (EventsAreVocabulary) failed: {command.Event!r} "
                        f"is not a value of {self.EventType}!"
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: StatesAreVocabulary.
        If StateType equals "relay.closed.or.open", "hp.boss.state" or
        "pico.cycler.state", every Commands entry's ToState SHALL be a value
        of relay.closed.or.open:000, hp.boss.state:000 or
        pico.cycler.state:000 respectively.
        """
        valid = STATE_VOCABULARY.get(self.StateType)
        if valid is not None:
            for command in self.Commands:
                if command.ToState not in valid:
                    raise ValueError(
                        f"Axiom 3 (StatesAreVocabulary) failed: {command.ToState!r} "
                        f"is not a value of {self.StateType}!"
                    )
        return self

from typing import Literal

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    AquastatControl,
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangeKeepSend,
    ChangePrimaryPumpControl,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    HeatPumpControl,
    HeatcallSource,
    HpLoopKeepSend,
    PrimaryPumpControl,
    RelayClosedOrOpen,
    RelayWiringConfig,
    StoreFlowRelay,
    ChangeHeatcallSource,
)
from gwsproto.property_format import (
    SpaceheatName, LeftRightDotStr
)

KNOWN_EVENT_ENUMS = {
    ChangeRelayState.enum_name(): ChangeRelayState,
    ChangeStoreFlowRelay.enum_name(): ChangeStoreFlowRelay,
    ChangeHeatPumpControl.enum_name(): ChangeHeatPumpControl,
    ChangeAquastatControl.enum_name(): ChangeAquastatControl,
    ChangePrimaryPumpControl.enum_name(): ChangePrimaryPumpControl,
    ChangeKeepSend.enum_name(): ChangeKeepSend,
    ChangeHeatcallSource.enum_name(): ChangeHeatcallSource,
}

KNOWN_STATE_ENUMS = {
    RelayClosedOrOpen.enum_name(): RelayClosedOrOpen,
    StoreFlowRelay.enum_name(): StoreFlowRelay,
    HeatPumpControl.enum_name(): HeatPumpControl,
    AquastatControl.enum_name(): AquastatControl,
    PrimaryPumpControl.enum_name(): PrimaryPumpControl,
    HpLoopKeepSend.enum_name(): HpLoopKeepSend,
    HeatcallSource.enum_name(): HeatcallSource,
}

EVENT_TO_STATE = {
    (
        ChangeRelayState.enum_name(),
        RelayClosedOrOpen.enum_name(),
    ): {
        ChangeRelayState.CloseRelay: RelayClosedOrOpen.RelayClosed,
        ChangeRelayState.OpenRelay: RelayClosedOrOpen.RelayOpen,
    },
    (
        ChangeStoreFlowRelay.enum_name(),
        StoreFlowRelay.enum_name(),
    ): {
        ChangeStoreFlowRelay.DischargeStore: StoreFlowRelay.DischargingStore,
        ChangeStoreFlowRelay.ChargeStore: StoreFlowRelay.ChargingStore,
    },
    (
        ChangeHeatPumpControl.enum_name(),
        HeatPumpControl.enum_name(),
    ): {
        ChangeHeatPumpControl.SwitchToTankAquastat: HeatPumpControl.BufferTankAquastat,
        ChangeHeatPumpControl.SwitchToScada: HeatPumpControl.Scada,
    },
    (
        ChangeAquastatControl.enum_name(),
        AquastatControl.enum_name(),
    ): {
        ChangeAquastatControl.SwitchToBoiler: AquastatControl.Boiler,
        ChangeAquastatControl.SwitchToScada: AquastatControl.Scada,
    },
    (
        ChangePrimaryPumpControl.enum_name(),
        PrimaryPumpControl.enum_name(),
    ): {
        ChangePrimaryPumpControl.SwitchToHeatPump: PrimaryPumpControl.HeatPump,
        ChangePrimaryPumpControl.SwitchToScada: PrimaryPumpControl.Scada,
    },
    (
        ChangeKeepSend.enum_name(),
        HpLoopKeepSend.enum_name(),
    ): {
        ChangeKeepSend.ChangeToKeepLess: HpLoopKeepSend.SendMore,
        ChangeKeepSend.ChangeToKeepMore: HpLoopKeepSend.SendLess,
    },
    (
        ChangeHeatcallSource.enum_name(),
        HeatcallSource.enum_name(),
    ): {
        ChangeHeatcallSource.SwitchToWallThermostat: HeatcallSource.WallThermostat,
        ChangeHeatcallSource.SwitchToScada: HeatcallSource.Scada,
    },
}


class RelayActorConfig(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/relay.actor.config/003
    """

    ChannelName: SpaceheatName
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
    Version: Literal["003"] = "003"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: RelayEventEnumConsistency.
        If the event type is the name of a known enum, then the DeEnergizingEvent, EnergizingEvent pair are the values of that enum.
        """
        event_enum = KNOWN_EVENT_ENUMS.get(self.EventType)
        if event_enum is not None:
            valid_values = set(event_enum.values())
            invalid = [
                event
                for event in [self.DeEnergizingEvent, self.EnergizingEvent]
                if event not in valid_values
            ]
            if invalid:
                raise ValueError(
                    "Axiom 1 (RelayEventEnumConsistency) failed: "
                    f"{invalid} not in {self.EventType} values {sorted(valid_values)}"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: RelayStateEnumConsistency.
        If the state type is the name of a known enum, then the DeEnergizedState, EnergizedState pair are the values of that enum.
        """
        state_enum = KNOWN_STATE_ENUMS.get(self.StateType)
        if state_enum is not None:
            valid_values = set(state_enum.values())
            invalid = [
                state
                for state in [self.DeEnergizedState, self.EnergizedState]
                if state not in valid_values
            ]
            if invalid:
                raise ValueError(
                    "Axiom 2 (RelayStateEnumConsistency) failed: "
                    f"{invalid} not in {self.StateType} values {sorted(valid_values)}"
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: RelayEventStateMatch.
         E.g. if RelayOpen is the EnergizedState then the EnergizingEvent is OpenRelay.
        """
        expected_states = EVENT_TO_STATE.get((self.EventType, self.StateType))
        if expected_states is not None:
            expected_de_energized = expected_states.get(self.DeEnergizingEvent)
            expected_energized = expected_states.get(self.EnergizingEvent)
            if expected_de_energized != self.DeEnergizedState:
                raise ValueError(
                    "Axiom 3 (RelayEventStateMatch) failed: "
                    f"DeEnergizingEvent {self.DeEnergizingEvent} implies "
                    f"DeEnergizedState {expected_de_energized}, not {self.DeEnergizedState}"
                )
            if expected_energized != self.EnergizedState:
                raise ValueError(
                    "Axiom 3 (RelayEventStateMatch) failed: "
                    f"EnergizingEvent {self.EnergizingEvent} implies "
                    f"EnergizedState {expected_energized}, not {self.EnergizedState}"
                )
        return self

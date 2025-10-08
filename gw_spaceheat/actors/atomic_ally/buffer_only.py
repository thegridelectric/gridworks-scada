import time
from actors.atomic_ally.atomic_ally_base import AtomicAllyBase, AaBufferOnlyEvent
from gwsproto.named_types import AllyGivesUp
from transitions import Machine
from gw.enums import GwStrEnum
from enum import auto
from typing import List


class AaBufferOnlyState(GwStrEnum):
    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    HpOffOilBoilerTankAquastat = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "aa.buffer_only.state"

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]


class AaBufferOnlyEvent(GwStrEnum):
    NoMoreElec = auto()
    BufferFull = auto()
    ChargeBuffer = auto()
    TemperaturesAvailable = auto()
    StartHackOil = auto()
    StopHackOil = auto()
    GoDormant = auto()
    WakeUp = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "aa.buffer_only.event"


class BufferOnlyAtomicAllyStrategy(AtomicAllyBase):
    states = AaBufferOnlyState.values()

    transitions = (
        [
        # Initializing
        {"trigger": "ChargeBuffer", "source": "Initializing", "dest": "HpOn"},
        {"trigger": "BufferFull", "source": "Initializing", "dest": "HpOff"},
        {"trigger": "NoMoreElec", "source": "Initializing", "dest": "HpOff"},
        # 1 Starting at: HP on, Store off ============= HP -> buffer
        {"trigger": "BufferFull", "source": "HpOn", "dest": "HpOff"},
        {"trigger": "NoMoreElec", "source": "HpOn", "dest": "HpOff"},
        # 2 Starting at: HP off, Store off ============ idle
        {"trigger": "ChargeBuffer", "source": "HpOff", "dest": "HpOn"},
        # 3 Oil boiler on
    ] + [
        {"trigger": "StartHackOil", "source": state, "dest": "HpOffOilBoilerTankAquastat"}
        for state in states if state not in  ["Dormant", "HpOffOilBoilerTankAquastat"]
    ] + [
        {"trigger":"StopHackOil", "source": "HpOffOilBoilerTankAquastat", "dest": "Initializing"}
        # Going dormant and waking up
    ] + [
        {"trigger": "GoDormant", "source": state, "dest": "Dormant"} for state in states if state != "Dormant"
    ] + [
        {"trigger":"WakeUp", "source": "Dormant", "dest": "Initializing"}
    ] 
    )

    def __init__(self, name: str, services):
        super().__init__(name, services)
        # State machine
        self.machine = Machine(
            model=self,
            states=BufferOnlyAtomicAllyStrategy.states,
            transitions=BufferOnlyAtomicAllyStrategy.transitions,
            initial=AaBufferOnlyState.Dormant,
            send_event=True,
        )     
        self.state: AaBufferOnlyState = AaBufferOnlyState.Dormant
        self.prev_state: AaBufferOnlyState = AaBufferOnlyState.Dormant 
        self.time_buffer_full = 0

    def engage_brain(self) -> None:
        self.log(f"State: {self.state}")
        if self.state not in [AaBufferOnlyState.Dormant, 
                              AaBufferOnlyState.HpOffOilBoilerTankAquastat]:
            self.get_latest_temperatures()

            if self.state == AaBufferOnlyState.Initializing:
                if self.temperatures_available: #TODO
                    self.no_temps_since = None
                    if self.hp_should_be_off():
                        self.trigger_event(AaBufferOnlyEvent.NoMoreElec)
                    elif self.is_buffer_full(really_full=True):
                        self.log("Buffer is as full as can be")
                        self.time_buffer_full = int(time.time())
                        self.trigger_event(AaBufferOnlyEvent.BufferFull)
                        # TODO: send message to ATN saying the EnergyInstruction will be violated
                    else:
                        self.trigger_event(AaBufferOnlyEvent.ChargeBuffer)
                            
                else: # temperatures not avalable
                    if self.no_temps_since is None:
                        self.no_temps_since = int(time.time()) # start the clock
                    elif time.time() - self.no_temps_since > self.NO_TEMPS_BAIL_MINUTES * 60:
                        self.log("Cannot suit up - missing temperatures!")
                        self._send_to(
                            self.primary_scada,
                            AllyGivesUp(Reason="Missing temperatures required for operation"))
                        return
                    if self.hp_should_be_off():
                        self.turn_off_HP() 

            # 1
            elif self.state == AaBufferOnlyState.HpOn:
                if self.hp_should_be_off():
                    self.trigger_event(AaBufferOnlyEvent.NoMoreElec)
                elif self.is_buffer_full(really_full=True):
                    self.log("Buffer is as full as can be")
                    self.time_buffer_full = int(time.time())
                    self.trigger_event(AaBufferOnlyEvent.BufferFull)
                    # TODO: send message to ATN saying the EnergyInstruction will be violated

            # 2
            elif self.state == AaBufferOnlyState.HpOff:
                if not self.hp_should_be_off() and time.time()-self.time_buffer_full>15*60:
                    self.trigger_event(AaBufferOnlyEvent.ChargeBuffer)


    def update_relays(self) -> None:
        self.log(f"update_relays with previous_state {self.prev_state} and state {self.state}")
        if self.state == AaBufferOnlyState.Dormant:
            return
        if self.state == AaBufferOnlyState.Initializing:
            if self.hp_should_be_off():
                self.turn_off_HP()
            return

        if self.prev_state == AaBufferOnlyState.HpOffOilBoilerTankAquastat:
            self.hp_failsafe_switch_to_scada()
            self.aquastat_ctrl_switch_to_scada()
        if "HpOn" not in self.prev_state and "HpOn" in self.state:
            self.turn_on_HP()
        if "HpOff" not in self.prev_state and "HpOff" in self.state:
            self.turn_off_HP()
        if self.state == AaBufferOnlyState.HpOffOilBoilerTankAquastat.value:
            self.hp_failsafe_switch_to_aquastat()
            self.aquastat_ctrl_switch_to_boiler()
        else:
            self.hp_failsafe_switch_to_scada()
            self.aquastat_ctrl_switch_to_scada()

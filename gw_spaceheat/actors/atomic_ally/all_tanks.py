import time
from actors.atomic_ally.atomic_ally_base import AtomicAllyBase
from gwsproto.named_types import AllyGivesUp
from transitions import Machine
from gw.enums import GwStrEnum
from enum import auto
from typing import List
from gwsproto.enums import AtomicAllyState, AtomicAllyEvent

class AaAllTanksState(GwStrEnum):
    Initializing = auto()
    HpOnStoreOff = auto()
    HpOnStoreCharge = auto()
    HpOffStoreOff = auto()
    HpOffStoreDischarge = auto()
    HpOffOilBoilerTankAquastat = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "aa.all.tanks.state"

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]


class AaAllTanksEvent(GwStrEnum):
    NoElecBufferEmpty = auto()
    NoElecBufferFull = auto()
    ElecBufferEmpty = auto()
    ElecBufferFull = auto()
    NoMoreElec = auto()
    TemperaturesAvailable = auto()
    StartHackOil = auto()
    StopHackOil = auto()
    GoDormant = auto()
    WakeUp = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "aa.all.tanks.event"


class AllTanksAtomicAllyStrategy(AtomicAllyBase):
    states = AaAllTanksState.values()

    transitions = (
        [
        # Initializing
        {"trigger": "NoElecBufferEmpty", "source": "Initializing", "dest": "HpOffStoreDischarge"},
        {"trigger": "NoElecBufferFull", "source": "Initializing", "dest": "HpOffStoreOff"},
        {"trigger": "ElecBufferEmpty", "source": "Initializing", "dest": "HpOnStoreOff"},
        {"trigger": "ElecBufferFull", "source": "Initializing", "dest": "HpOnStoreCharge"},
        # 1 Starting at: HP on, Store off ============= HP -> buffer
        {"trigger": "ElecBufferFull", "source": "HpOnStoreOff", "dest": "HpOnStoreCharge"},
        {"trigger": "NoMoreElec", "source": "HpOnStoreOff", "dest": "HpOffStoreOff"},
        # 2 Starting at: HP on, Store charging ======== HP -> storage
        {"trigger": "ElecBufferEmpty", "source": "HpOnStoreCharge", "dest": "HpOnStoreOff"},
        {"trigger": "NoMoreElec", "source": "HpOnStoreCharge", "dest": "HpOffStoreOff"},
        # 3 Starting at: HP off, Store off ============ idle
        {"trigger": "NoElecBufferEmpty", "source": "HpOffStoreOff", "dest": "HpOffStoreDischarge"},
        {"trigger": "ElecBufferEmpty", "source": "HpOffStoreOff", "dest": "HpOnStoreOff"},
        {"trigger": "ElecBufferFull", "source": "HpOffStoreOff", "dest": "HpOnStoreCharge"},
        # 4 Starting at: Hp off, Store discharging ==== Storage -> buffer
        {"trigger": "NoElecBufferFull", "source": "HpOffStoreDischarge", "dest": "HpOffStoreOff"},
        {"trigger": "ElecBufferEmpty", "source": "HpOffStoreDischarge", "dest": "HpOnStoreOff"},
        {"trigger": "ElecBufferFull", "source": "HpOffStoreDischarge", "dest": "HpOnStoreCharge"},
        # 5 Oil boiler on during onpeak
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
            states=AllTanksAtomicAllyStrategy.states,
            transitions=AllTanksAtomicAllyStrategy.transitions,
            initial=AaAllTanksState.Dormant,
            send_event=True,
        )     
        self.state: AaAllTanksState = AaAllTanksState.Dormant
        self.prev_state: AaAllTanksState = AaAllTanksState.Dormant 

    def engage_brain(self) -> None:
        self.log(f"State: {self.state}")
        if self.state not in [AaAllTanksState.Dormant, 
                              AaAllTanksState.HpOffOilBoilerTankAquastat]:
            self.get_latest_temperatures()

            if self.state == AaAllTanksState.Initializing:
                if self.temperatures_available: 
                    self.no_temps_since = None
                    if self.hp_should_be_off():
                        if (
                            self.is_buffer_empty()
                            and not self.is_storage_colder_than_buffer()
                        ):
                            self.trigger_event(AtomicAllyEvent.NoElecBufferEmpty)
                        else:
                            self.trigger_event(AtomicAllyEvent.NoElecBufferFull)
                    else:
                        if self.is_buffer_empty() or self.is_storage_full():
                            self.trigger_event(AtomicAllyEvent.ElecBufferEmpty)
                        else:
                            self.trigger_event(AtomicAllyEvent.ElecBufferFull)
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
            elif self.state == AaAllTanksState.HpOnStoreOff:
                if self.hp_should_be_off():
                    self.trigger_event(AtomicAllyEvent.NoMoreElec)
                elif self.is_buffer_full() and not self.is_storage_full():
                    self.trigger_event(AtomicAllyEvent.ElecBufferFull)
                elif self.is_buffer_full(really_full=True):
                    if not self.storage_declared_full or time.time()-self.storage_full_since>15*60:
                        self.trigger_event(AtomicAllyEvent.ElecBufferFull)
                    if self.storage_declared_full and time.time()-self.storage_full_since<15*60:
                        self.log("Both storage and buffer are as full as can be")
                        self.trigger_event(AtomicAllyEvent.NoMoreElec)
                        # TODO: send message to ATN saying the EnergyInstruction will be violated

            # 2
            elif self.state == AaAllTanksState.HpOnStoreCharge:
                if self.hp_should_be_off():
                    self.trigger_event(AtomicAllyEvent.NoMoreElec)
                elif self.is_buffer_empty() or self.is_storage_full():
                    self.trigger_event(AtomicAllyEvent.ElecBufferEmpty)

            # 3
            elif self.state == AaAllTanksState.HpOffStoreOff:
                if self.hp_should_be_off():
                    if (
                        self.is_buffer_empty()
                        and not self.is_storage_colder_than_buffer()
                    ):
                        self.trigger_event(AtomicAllyEvent.NoElecBufferEmpty)
                else:
                    if self.is_buffer_empty() or self.is_storage_full():
                        self.trigger_event(AtomicAllyEvent.ElecBufferEmpty)
                    else:
                        self.trigger_event(AtomicAllyEvent.ElecBufferFull)

            # 4
            elif self.state == AaAllTanksState.HpOffStoreDischarge:
                if self.hp_should_be_off():
                    if (
                        self.is_buffer_full()
                        or self.is_storage_colder_than_buffer()
                    ):
                        self.trigger_event(AtomicAllyEvent.NoElecBufferFull)
                else:
                    if self.is_buffer_empty() or self.is_storage_full():
                        self.trigger_event(AtomicAllyEvent.ElecBufferEmpty)
                    else:
                        self.trigger_event(AtomicAllyEvent.ElecBufferFull)

    def update_relays(self) -> None:
        self.log(f"update_relays with previous_state {self.prev_state} and state {self.state}")
        if self.state == AaAllTanksState.Dormant:
            return
        if self.state == AaAllTanksState.Initializing:
            if self.hp_should_be_off():
                self.turn_off_HP()
            return

        if self.prev_state == AaAllTanksState.HpOffOilBoilerTankAquastat:
            self.hp_failsafe_switch_to_scada()
            self.aquastat_ctrl_switch_to_scada()
        if "HpOn" not in self.prev_state and "HpOn" in self.state:
            self.turn_on_HP()
        if "HpOff" not in self.prev_state and "HpOff" in self.state:
            self.turn_off_HP()
        if "StoreDischarge" in self.state:
            self.turn_on_store_pump()
        else:
            self.turn_off_store_pump()  
        if "StoreCharge" in self.state:
            self.valved_to_charge_store()
        else:
            self.valved_to_discharge_store()
        if self.state == AaAllTanksState.HpOffOilBoilerTankAquastat.value:
            self.hp_failsafe_switch_to_aquastat()
            self.aquastat_ctrl_switch_to_boiler()
        else:
            self.hp_failsafe_switch_to_scada()
            self.aquastat_ctrl_switch_to_scada()

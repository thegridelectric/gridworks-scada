import time
from datetime import datetime
from typing import Optional

from actors.local_control.tou_base import LocalControlTouBase
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import (
    LocalControlAllTanksEvent, LocalControlAllTanksState, LocalControlTopState, 
    SeasonalStorageMode
)
    
from gwsproto.named_types import SingleMachineState
from transitions import Machine

from scada_app_interface import ScadaAppInterface



class AllTanksTouLocalControl(LocalControlTouBase):
    states = LocalControlAllTanksState.values()

    transitions = [
            # Initializing
            {"trigger": "OnPeakBufferEmpty", "source": "Initializing", "dest": "HpOffStoreDischarge"},
            {"trigger": "OnPeakBufferFull", "source": "Initializing", "dest": "HpOffStoreOff"},
            {"trigger": "OnPeakStorageColderThanBuffer", "source": "Initializing", "dest": "HpOffStoreOff"},
            {"trigger": "OffPeakBufferEmpty", "source": "Initializing", "dest": "HpOnStoreOff"},
            {"trigger": "OffPeakBufferFullStorageReady", "source": "Initializing", "dest": "HpOffStoreOff"},
            {"trigger": "OffPeakBufferFullStorageNotReady", "source": "Initializing", "dest": "HpOnStoreCharge"},
            # Starting at: HP on, Store off ============= HP -> buffer
            {"trigger": "OffPeakBufferFullStorageNotReady", "source": "HpOnStoreOff", "dest": "HpOnStoreCharge"},
            {"trigger": "OffPeakBufferFullStorageReady", "source": "HpOnStoreOff", "dest": "HpOffStoreOff"},
            {"trigger": "OnPeakStart", "source": "HpOnStoreOff", "dest": "HpOffStoreOff"},
            # Starting at: HP on, Store charging ======== HP -> storage
            {"trigger": "OffPeakBufferEmpty", "source": "HpOnStoreCharge", "dest": "HpOnStoreOff"},
            {"trigger": "OffPeakStorageReady", "source": "HpOnStoreCharge", "dest": "HpOnStoreOff"},
            {"trigger": "OnPeakStart", "source": "HpOnStoreCharge", "dest": "HpOffStoreOff"},
            # Starting at: HP off, Store off ============ idle
            {"trigger": "OnPeakBufferEmpty", "source": "HpOffStoreOff", "dest": "HpOffStoreDischarge"},
            {"trigger": "OffPeakBufferEmpty", "source": "HpOffStoreOff", "dest": "HpOnStoreOff"},
            {"trigger": "OffPeakStorageNotReady", "source": "HpOffStoreOff", "dest": "HpOnStoreCharge"},
            # Starting at: Hp off, Store discharging ==== Storage -> buffer
            {"trigger": "OnPeakBufferFull", "source": "HpOffStoreDischarge", "dest": "HpOffStoreOff"},
            {"trigger": "OnPeakStorageColderThanBuffer", "source": "HpOffStoreDischarge", "dest": "HpOffStoreOff"},
            {"trigger": "OffPeakStart", "source": "HpOffStoreDischarge", "dest": "HpOffStoreOff"},
        ] + [
                {"trigger": "GoDormant", "source": state, "dest": "Dormant"}
                for state in states if state != "Dormant"
        ] + [{"trigger":"WakeUp", "source": "Dormant", "dest": "Initializing"}]
    

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        if self.settings.seasonal_storage_mode != SeasonalStorageMode.AllTanks:
            raise Exception(f"Expect WinterTou LocalControl, got {self.settings.seasonal_storage_mode}")

        self.storage_declared_ready = False
        self.time_hp_turned_on = None
        self.full_storage_energy: Optional[float] = None
        
        self.machine = Machine(
            model=self,
            states=AllTanksTouLocalControl.states,
            transitions=AllTanksTouLocalControl.transitions,
            initial=LocalControlAllTanksState.Initializing,
            send_event=True,
        )   
        self.state: LocalControlAllTanksState = LocalControlAllTanksState.Initializing  

    def trigger_normal_event(self, event: LocalControlAllTanksEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.state
        
        if event == LocalControlAllTanksEvent.OnPeakStart:
            self.OnPeakStart()
        elif event  == LocalControlAllTanksEvent.OffPeakStart:
            self.OffPeakStart()
        elif event  == LocalControlAllTanksEvent.OnPeakBufferFull:
            self.OnPeakBufferFull()
        elif event  == LocalControlAllTanksEvent.OffPeakBufferFullStorageNotReady:
            self.OffPeakBufferFullStorageNotReady()
        elif event  == LocalControlAllTanksEvent.OffPeakBufferFullStorageReady:
            self.OffPeakBufferFullStorageReady ()
        elif event  == LocalControlAllTanksEvent.OffPeakBufferEmpty:
            self.OffPeakBufferEmpty()
        elif event  == LocalControlAllTanksEvent.OnPeakBufferEmpty:
            self.OnPeakBufferEmpty()
        elif event  == LocalControlAllTanksEvent.OffPeakStorageReady:
            self.OffPeakStorageReady()
        elif event  == LocalControlAllTanksEvent.OffPeakStorageNotReady:
            self.OffPeakStorageNotReady()
        elif event  == LocalControlAllTanksEvent.OnPeakStorageColderThanBuffer:
            self.OnPeakStorageColderThanBuffer()
        elif event  == LocalControlAllTanksEvent.TemperaturesAvailable:
            self.TemperaturesAvailable()
        elif event  == LocalControlAllTanksEvent.GoDormant:
            self.GoDormant()
        elif event  == LocalControlAllTanksEvent.WakeUp:
            self.WakeUp()
        else:
             raise Exception(f"Unkonnwn event {event}")


        self.log(f"{event}: {orig_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=LocalControlAllTanksState.enum_name(),
                State=self.state,
                UnixMs=now_ms,
                Cause=event
            )
        )
        
    def time_to_trigger_system_cold(self) -> bool:
        """
        Logic for triggering SystemCold (and moving to top state UsingNonElectricBackup).
        In winter, this means: 1) house is cold 2) buffer is really empty and 3) store is empty
        """
        return self.is_system_cold() # HACK FOR JAN 24th
        # return self.is_system_cold() and self.is_buffer_empty() and self.is_storage_empty()

    def normal_node_state(self) -> str:
        return self.state

    def is_initializing(self) -> bool:
        return self.state == LocalControlAllTanksState.Initializing

    def normal_node_goes_dormant(self) -> None:
        """GoDormant: Any -> Dormant for self.state"""
        if self.state != LocalControlAllTanksState.Dormant:
            self.trigger_normal_event(LocalControlAllTanksEvent.GoDormant)

    def normal_node_wakes_up(self) -> None:
        """WakeUp: Dormant -> Initializing for self.state"""
        if self.state == LocalControlAllTanksState.Dormant:
            self.trigger_normal_event(LocalControlAllTanksEvent.WakeUp)
            self.time_since_blind = None
            self.engage_brain()

    def engage_brain(self) -> None:
        """
        Manages the logic for the Normal top state, (ie. self.state)
        """
        if self.top_state != LocalControlTopState.Normal:
            self.log(f"brain is only for Normal top state, not {self.top_state}")
            return

        if self.state == LocalControlAllTanksState.Dormant:
            self.alert("Bad LocalControl State", "TopState Normal, state Dormant!")
            self.trigger_normal_event(LocalControlAllTanksEvent.WakeUp)
        
        if not self.actuators_initialized:
            self.initialize_actuators()

        previous_state = self.state

        if self.is_onpeak():
            self.storage_declared_ready = False
            self.full_storage_energy = None

        time_now = datetime.now(self.timezone)
        if ((time_now.hour==6 or time_now.hour==16) and time_now.minute>57) or self.zone_setpoints=={}:
            self.get_zone_setpoints()
        
        if not (self.heating_forecast and self.buffer_temps_available):
            self.fill_missing_store_temps()
            if self.time_since_blind is None:
                self.time_since_blind = time.time()
            elif time.time() - self.time_since_blind > self.BLIND_MINUTES*60:
                self.log("Scada is missing forecasts and/or critical temperatures since at least 5 min.")
                self.log("Moving into ScadaBlind top state")
                self.trigger_missing_data()
            elif self.time_since_blind is not None:
                self.log(f"Blind since {int(time.time() - self.time_since_blind)} seconds")
        else:
            if self.time_since_blind is not None:
                self.time_since_blind = None
            if self.state==LocalControlAllTanksState.Initializing:
                if self.buffer_temps_available and self.data.channel_has_value(H0CN.required_energy):
                    if self.is_onpeak():
                        if self.is_buffer_empty():
                            if self.is_storage_colder_than_buffer():
                                self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakStorageColderThanBuffer)
                            else:
                                self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakBufferEmpty)
                        else:
                            self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakBufferFull)
                    else:
                        if self.is_buffer_empty():
                            self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferEmpty)
                        else:
                            if self.is_storage_ready():
                                self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferFullStorageReady)
                            else:
                                self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferFullStorageNotReady)

            elif self.state==LocalControlAllTanksState.HpOnStoreOff:
                if self.is_onpeak():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakStart)
                elif self.is_buffer_full():
                    if self.is_storage_ready():
                        self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferFullStorageReady)
                    else:

                        if self.usable_kwh < self.required_kwh:
                            self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferFullStorageNotReady)
                        else:
                            self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferFullStorageReady)
                
            elif self.state==LocalControlAllTanksState.HpOnStoreCharge:
                if self.is_onpeak():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakStart)
                elif self.is_buffer_empty():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferEmpty)
                elif self.is_storage_ready():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakStorageReady)
                
            elif self.state==LocalControlAllTanksState.HpOffStoreOff:
                if self.is_onpeak():
                    if self.is_buffer_empty() and not self.is_storage_colder_than_buffer():
                        self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakBufferEmpty)
                else:
                    if self.is_buffer_empty():
                        self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakBufferEmpty)
                    elif not self.is_storage_ready():

                        if self.storage_declared_ready:
                            if self.full_storage_energy is None:
                                if self.usable_kwh > 0.9 * self.required_kwh:
                                    self.log("The storage was already declared ready during this off-peak period")
                                else:
                                    self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakStorageNotReady)
                            else:
                                if self.usable_kwh > 0.9 * self.full_storage_energy:
                                    self.log("The storage was already declared full during this off-peak period")
                                else:
                                    self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakStorageNotReady)
                        else:
                            self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakStorageNotReady)

            elif self.state==LocalControlAllTanksState.HpOffStoreDischarge:
                if not self.is_onpeak():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OffPeakStart)
                elif self.is_buffer_full():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakBufferFull)
                elif self.is_storage_colder_than_buffer():
                    self.trigger_normal_event(LocalControlAllTanksEvent.OnPeakStorageColderThanBuffer)

        if (self.state != previous_state) and self.top_state == LocalControlTopState.Normal:
            self.update_relays(previous_state)

    def update_relays(self, previous_state) -> None:
        if self.top_state != LocalControlTopState.Normal:
            raise Exception("Can not go into update_relays if top state is not Normal")
        if self.state == LocalControlAllTanksState.Dormant or self.state == LocalControlAllTanksState.Initializing:
            return
        if "HpOn" not in previous_state and "HpOn" in self.state:
            self.turn_on_HP(from_node=self.normal_node)
            self.time_hp_turned_on = time.time()
        if "HpOff" not in previous_state and "HpOff" in self.state:
            self.turn_off_HP(from_node=self.normal_node)
            self.time_hp_turned_on = None
        if "StoreDischarge" in self.state:
            self.turn_on_store_pump(command_node=self.normal_node)
        else:
            self.turn_off_store_pump(command_node=self.normal_node)         
        if "StoreCharge" in self.state:
            self.valved_to_charge_store(from_node=self.normal_node)
        else:
            self.valved_to_discharge_store(from_node=self.normal_node)

    def is_storage_ready(self) -> bool:
        if self.usable_kwh >=self.required_kwh:
            self.log(f"Storage ready (usable {round(self.usable_kwh,1)} kWh >= required {round(self.required_kwh,1)} kWh)")
            self.storage_declared_ready = True
            return True
        else:
            if H0N.store_cold_pipe in self.latest_temps_f:
                check_temp_channel = H0N.store_cold_pipe
            elif H0N.hp_ewt in self.latest_temps_f:
                check_temp_channel = H0N.hp_ewt
            else:
                self.log("No EWT temperature channel found, not checking if storage is ready")
                return False
            if self.latest_temps_f[check_temp_channel] > self.params.MaxEwtF:
                self.log(f"{check_temp_channel}: {self.latest_temps_f[check_temp_channel]}. MaxEWT: {self.params.MaxEwtF} F")
                self.log(f"The storage is not ready, but the bottom is above the maximum EWT ({self.params.MaxEwtF} F).")
                self.log("The storage will therefore be considered ready, as we cannot charge it further.")
                self.full_storage_energy = self.usable_kwh
                self.storage_declared_ready = True
                return True
            self.log(f"Storage not ready (usable {round(self.usable_kwh,1)} kWh < required {round(self.required_kwh,1)} kWh)")
            return False


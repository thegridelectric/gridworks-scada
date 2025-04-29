
from typing import List, Optional
from enum import auto
import time
from datetime import datetime
from gw.enums import GwStrEnum
from transitions import Machine
from data_classes.house_0_names import H0N, H0CN

from actors.scada_interface import ScadaInterface
from actors.home_alone.home_alone_tou_base import HomeAloneTouBase
from named_types import SingleMachineState
from enums import HomeAloneStrategy, HomeAloneTopState


class HaShoulderState(GwStrEnum):
    Initializing = auto()
    HpOn = auto()
    HpOff = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "ha.shoulder.state"

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]

class HaShoulderEvent(GwStrEnum):
    OnPeakStart = auto()
    BufferFull = auto()
    BufferNeedsCharge = auto()
    TemperaturesAvailable = auto()
    GoDormant = auto()
    WakeUp = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "ha.shoulder.event"


class HomeAlone(HomeAloneTouBase):
    states = HaShoulderState.values()

    transitions = (
        [
        # Initializing
        {"trigger": "BufferNeedsCharge", "source": "Initializing", "dest": "HpOn"},
        {"trigger": "BufferFull", "source": "Initializing", "dest": "HpOff"},
        {"trigger": "OnPeakStart", "source": "Initializing", "dest": "HpOff"},
        # Starting at: HP on, Store off ============= HP -> buffer
        {"trigger": "BufferFull", "source": "HpOn", "dest": "HpOff"},
        {"trigger": "OnPeakStart", "source": "HpOn", "dest": "HpOff"},
        # Starting at: HP off, Store off ============ idle
        {"trigger": "BufferNeedsCharge", "source": "HpOff", "dest": "HpOn"},
    ] + [
            {"trigger": "GoDormant", "source": state, "dest": "Dormant"}
            for state in states if state != "Dormant"
    ] 
    + [{"trigger":"WakeUp", "source": "Dormant", "dest": "Initializing"}]
    )


    def __init__(self, name: str, services: ScadaInterface):
        super().__init__(name, services)
        if self.strategy != HomeAloneStrategy.ShoulderTou:
            raise Exception(f"Expect ShoulderTou HomeAloneStrategy, got {self.strategy}")

        self.buffer_declared_ready = False
        self.full_buffer_energy: Optional[float] = None # in kWh
         
        self.machine = Machine(
            model=self,
            states=HomeAlone.states,
            transitions=HomeAlone.transitions,
            initial=HaShoulderState.Initializing,
            send_event=True,
        )   
        self.state: HaShoulderState = HaShoulderState.Initializing 

    def trigger_normal_event(self, event: HaShoulderEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.state
        
        if event == HaShoulderEvent.OnPeakStart:
            self.OnPeakStart()
        elif event == HaShoulderEvent.BufferFull:
            self.BufferFull()
        elif event == HaShoulderEvent.BufferNeedsCharge:
            self.BufferNeedsCharge()
        elif event == HaShoulderEvent.TemperaturesAvailable:
            self.TemperaturesAvailable()
        elif event == HaShoulderEvent.GoDormant:
            self.GoDormant()
        elif event == HaShoulderEvent.WakeUp:
            self.WakeUp()
        else:
            raise Exception(f"do not know event {event}")

        self.log(f"{event}: {orig_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=HaShoulderState.enum_name(),
                State=self.state,
                UnixMs=now_ms,
                Cause=event
            )
        )

    @property
    def temperature_channel_names(self) -> List[str]:
        return [
            H0CN.buffer.depth1, H0CN.buffer.depth2, H0CN.buffer.depth3, H0CN.buffer.depth4,
            H0CN.hp_ewt, H0CN.hp_lwt, H0CN.dist_swt, H0CN.dist_rwt, 
            H0CN.buffer_cold_pipe, H0CN.buffer_hot_pipe
        ]

    def time_to_trigger_house_cold_onpeak(self) -> bool:
        """
        Logic for triggering HouseColdOnpeak (and moving to top state UsingBakupOnpeak).

        In shoulder, this means:1) its onpeak  2) house is cold 3) buffer is really empty

        """
        return self.is_onpeak() and self.is_house_cold() and self.is_buffer_empty(really_empty=True)

    def normal_node_state(self) -> str:
        return self.state

    def is_initializing(self) -> bool:
        return self.state == HaShoulderState.Initializing

    def normal_node_goes_dormant(self) -> None:
        """Trigger GoDormant event"""
        if self.state != HaShoulderState.Dormant:
            self.trigger_normal_event(HaShoulderEvent.GoDormant)

    def normal_node_wakes_up(self) -> None:
        """WakeUp: Dormant -> Initializing for self.state and
        then engage brain"""
        if self.state == HaShoulderState.Dormant:
            self.trigger_normal_event(HaShoulderEvent.WakeUp)
            self.time_since_blind = None
            self.engage_brain()

    def engage_brain(self) -> None:
        """
        Manages the logic for the Normal top state, (ie. self.state)
        """
        if self.top_state != HomeAloneTopState.Normal:
            self.log(f"brain is only for Normal top state, not {self.top_state}")
            return

        if self.state == HaShoulderState.Dormant:
            self.alert("BadHomeAloneState", f"TopState Normal, state Dormant!")
            self.trigger_normal_event(HaShoulderEvent.WakeUp)

        if not self.relays_initialized:
            self.initialize_actuators()

        previous_state = self.state

        if self.is_onpeak():
            self.buffer_declared_ready = False
            self.full_buffer_energy = None
    
        if not (self.heating_forecast and self.temperatures_available()):
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

            if self.state==HaShoulderState.Initializing:
                if self.temperatures_available:
                    if self.is_onpeak():
                        self.trigger_normal_event(HaShoulderEvent.OnPeakStart)
                    else:
                        if self.is_buffer_empty() or not self.is_buffer_ready():
                            self.trigger_normal_event(HaShoulderEvent.BufferNeedsCharge)
                        else:
                            self.trigger_normal_event(HaShoulderEvent.BufferFull)

            elif self.state==HaShoulderState.HpOn:
                if self.is_onpeak():
                    self.trigger_normal_event(HaShoulderEvent.OnPeakStart)
                elif self.is_buffer_full() and self.is_buffer_ready():
                    self.trigger_normal_event(HaShoulderEvent.BufferFull)
                
            elif self.state==HaShoulderState.HpOff:
                if not self.is_onpeak():
                    if self.is_buffer_empty():
                        self.trigger_normal_event(HaShoulderEvent.BufferNeedsCharge)
                    elif not self.is_buffer_ready():
                        usable = self.data.latest_channel_values[H0N.usable_energy] / 1000
                        required = self.data.latest_channel_values[H0N.required_energy] / 1000
                        if self.buffer_declared_ready:
                            if self.full_buffer_energy is None:
                                if usable > 0.9*required:
                                    self.log("The buffer was already declared ready during this off-peak period")
                                else:
                                    self.trigger_normal_event(HaShoulderEvent.BufferNeedsCharge)
                            else:
                                if usable > 0.7*self.full_buffer_energy:
                                    self.log("The buffer was already declared full during this off-peak period")
                                else:
                                    self.trigger_normal_event(HaShoulderEvent.BufferNeedsCharge)
                        else:
                            self.trigger_normal_event(HaShoulderEvent.BufferNeedsCharge)          

        if (self.state != previous_state) and self.top_state == HomeAloneTopState.Normal:
            self.update_relays(previous_state)

    def update_relays(self, previous_state) -> None:
        if self.top_state != HomeAloneTopState.Normal:
            raise Exception("Can not go into update_relays if top state is not Normal")
        if self.state == HaShoulderState.Dormant or self.state == HaShoulderState.Initializing:
            return
        if previous_state != HaShoulderState.HpOn and self.state == HaShoulderState.HpOn:
            self.turn_on_HP(from_node=self.normal_node)
        if previous_state != HaShoulderState.HpOff and self.state == HaShoulderState.HpOff:
            self.turn_off_HP(from_node=self.normal_node)

    def is_buffer_empty(self, really_empty=False) -> bool:
        if H0CN.buffer.depth2 in self.latest_temperatures:
            if really_empty:
                buffer_empty_ch = H0CN.buffer.depth1
            else:
                buffer_empty_ch = H0CN.buffer.depth2
        elif H0CN.dist_swt in self.latest_temperatures:
            buffer_empty_ch = H0CN.dist_swt
        else:
            self.alert(summary="buffer_empty_fail", details="Impossible to know if the buffer is empty!")
            return False
        if self.heating_forecast is None:
            max_rswt_next_3hours = 160
            max_deltaT_rswt_next_3_hours = 20
        else:
            max_rswt_next_3hours = max(self.heating_forecast.RswtF[:3])
            max_deltaT_rswt_next_3_hours = max(self.heating_forecast.RswtDeltaTF[:3])
        min_buffer = round(max_rswt_next_3hours - max_deltaT_rswt_next_3_hours,1)
        buffer_empty_ch_temp = round(self.to_fahrenheit(self.latest_temperatures[buffer_empty_ch]/1000),1)
        if buffer_empty_ch_temp < min_buffer:
            self.log(f"Buffer empty ({buffer_empty_ch}: {buffer_empty_ch_temp} < {min_buffer} F)")
            return True
        else:
            self.log(f"Buffer not empty ({buffer_empty_ch}: {buffer_empty_ch_temp} >= {min_buffer} F)")
            return False 

    def is_buffer_full(self) -> bool:
        if H0CN.buffer.depth4 in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer.depth4
        elif H0CN.buffer_cold_pipe in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer_cold_pipe
        elif H0CN.hp_ewt in self.latest_temperatures:
            buffer_full_ch = H0CN.hp_ewt
        else:
            self.alert(summary="buffer_full_fail", details="Impossible to know if the buffer is full!")
            return False
        if self.heating_forecast is None:
            max_buffer = 170
        else:
            max_buffer = round(max(self.heating_forecast.RswtF[:3]),1)
        buffer_full_ch_temp = round(self.to_fahrenheit(self.latest_temperatures[buffer_full_ch]/1000),1)
        if buffer_full_ch_temp > max_buffer:
            self.log(f"Buffer full ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F)")
            return True
        else:
            self.log(f"Buffer not full ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F)")
            return False

    def is_buffer_ready(self) -> bool:
        if datetime.now(self.timezone).hour not in [5,6]+[14,15]:
            self.log("No onpeak period coming up soon.")
            self.buffer_declared_ready = False
            return True
        total_usable_kwh = self.data.latest_channel_values[H0N.usable_energy] / 1000
        required_onpeak = self.data.latest_channel_values[H0N.required_energy] / 1000

        # Add the requirement of getting to the start of onpeak
        now = datetime.now(self.timezone)
        onpeak_duration_hours = 5 if now.hour in [5,6] else 4
        onpeak_start_hour = 7 if now.hour in [5,6] else 16
        onpeak_start_time = self.timezone.localize(datetime(now.year, now.month, now.day, onpeak_start_hour, 0))
        time_to_onpeak = onpeak_start_time - now
        hours_to_onpeak = round(time_to_onpeak.total_seconds() / 3600, 2)
        self.log(f"There are {hours_to_onpeak} hours left to the start of onpeak")
        required_buffer_energy = required_onpeak * (1 + hours_to_onpeak/onpeak_duration_hours)

        if total_usable_kwh >= required_buffer_energy:
            self.log(f"Buffer ready for onpeak (usable {round(total_usable_kwh,1)} kWh >= required {round(required_buffer_energy,1)} kWh)")
            self.buffer_declared_ready = True
            return True
        else:
            if H0N.buffer_cold_pipe in self.latest_temperatures:
                self.log(f"Buffer cold pipe: {round(self.to_fahrenheit(self.latest_temperatures[H0N.buffer_cold_pipe]/1000),1)} F")
                if self.to_fahrenheit(self.latest_temperatures[H0N.buffer_cold_pipe]/1000) > self.params.MaxEwtF:
                    self.log(f"The buffer is not ready, but the bottom is above the maximum EWT ({self.params.MaxEwtF} F).")
                    self.log("The buffer will therefore be considered ready, as we cannot charge it further.")
                    self.full_buffer_energy = total_usable_kwh
                    self.buffer_declared_ready = True
                    return True
            self.log(f"Buffer not ready for onpeak (usable {round(total_usable_kwh,1)} kWh < required {round(required_buffer_energy,1)} kWh)")
            return False



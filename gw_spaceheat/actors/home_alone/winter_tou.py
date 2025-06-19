import time
from datetime import datetime
from enum import auto
from typing import List, Optional, cast

from actors.home_alone.home_alone_tou_base import HomeAloneTouBase
from actors.scada_interface import ScadaInterface
from data_classes.house_0_names import H0CN, H0N
from enums import HomeAloneStrategy, HomeAloneTopState
from gw.enums import GwStrEnum
from named_types import SingleMachineState
from transitions import Machine
from gwproto.named_types import PicoTankModuleComponentGt


class HaWinterState(GwStrEnum):
    Initializing = auto()
    HpOnStoreOff = auto()
    HpOnStoreCharge = auto()
    HpOffStoreOff = auto()
    HpOffStoreDischarge = auto()
    Dormant = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "ha.winter.state"

    @classmethod
    def values(cls) -> List[str]:
        return [elt.value for elt in cls]


class HaWinterEvent(GwStrEnum):
    OnPeakStart = auto()
    OffPeakStart = auto()
    OnPeakBufferFull = auto()
    OffPeakBufferFullStorageNotReady = auto()
    OffPeakBufferFullStorageReady = auto()
    OffPeakBufferEmpty = auto()
    OnPeakBufferEmpty = auto()
    OffPeakStorageReady = auto()
    OffPeakStorageNotReady = auto()
    OnPeakStorageColderThanBuffer = auto()
    TemperaturesAvailable = auto()
    GoDormant = auto()
    WakeUp = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "ha.winter.event"

class WinterTouHomeAlone(HomeAloneTouBase):
    states = HaWinterState.values()

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
            {"trigger": "OffPeakStorageReady", "source": "HpOnStoreCharge", "dest": "HpOffStoreOff"},
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
    

    def __init__(self, name: str, services: ScadaInterface):
        super().__init__(name, services)
        if self.strategy != HomeAloneStrategy.WinterTou:
            raise Exception(f"Expect WinterTou HomeAloneStrategy, got {self.strategy}")

        self.storage_declared_ready = False
        self.full_storage_energy: Optional[float] = None
        
        self.machine = Machine(
            model=self,
            states=WinterTouHomeAlone.states,
            transitions=WinterTouHomeAlone.transitions,
            initial=HaWinterState.Initializing,
            send_event=True,
        )   
        self.state: HaWinterState = HaWinterState.Initializing  

    def trigger_normal_event(self, event: HaWinterEvent) -> None:
        now_ms = int(time.time() * 1000)
        orig_state = self.state
        
        if event == HaWinterEvent.OnPeakStart:
            self.OnPeakStart()
        elif event  == HaWinterEvent.OffPeakStart:
            self.OffPeakStart()
        elif event  == HaWinterEvent.OnPeakBufferFull:
            self.OnPeakBufferFull()
        elif event  == HaWinterEvent.OffPeakBufferFullStorageNotReady:
            self.OffPeakBufferFullStorageNotReady()
        elif event  == HaWinterEvent.OffPeakBufferFullStorageReady:
            self.OffPeakBufferFullStorageReady ()
        elif event  == HaWinterEvent.OffPeakBufferEmpty:
            self.OffPeakBufferEmpty()
        elif event  == HaWinterEvent.OnPeakBufferEmpty:
            self.OnPeakBufferEmpty()
        elif event  == HaWinterEvent.OffPeakStorageReady:
            self.OffPeakStorageReady()
        elif event  == HaWinterEvent.OffPeakStorageNotReady:
            self.OffPeakStorageNotReady()
        elif event  == HaWinterEvent.OnPeakStorageColderThanBuffer:
            self.OnPeakStorageColderThanBuffer()
        elif event  == HaWinterEvent.OnPeakStorageColderThanBuffer:
            self.OnPeakStorageColderThanBuffer()
        elif event  == HaWinterEvent.TemperaturesAvailable:
            self.TemperaturesAvailable()
        elif event  == HaWinterEvent.GoDormant:
            self.GoDormant()
        elif event  == HaWinterEvent.WakeUp:
            self.WakeUp()
        else:
             raise Exception(f"Unkonnwn event {event}")


        self.log(f"{event}: {orig_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.normal_node.handle,
                StateEnum=HaWinterState.enum_name(),
                State=self.state,
                UnixMs=now_ms,
                Cause=event
            )
        )

    @property
    def temperature_channel_names(self) -> List[str]:
        '''Default is 3 layers per tank but can be 4 if PicoAHwUid is specified'''
        buffer_depths = [H0CN.buffer.depth1, H0CN.buffer.depth2, H0CN.buffer.depth3]
        tank_depths = [depth for tank in self.cn.tank.values() for depth in [tank.depth1, tank.depth2, tank.depth3]]
        if cast(PicoTankModuleComponentGt, self.layout.nodes['buffer'].component).PicoAHwUid:
            buffer_depths = [H0CN.buffer.depth1, H0CN.buffer.depth2, H0CN.buffer.depth3, H0CN.buffer.depth4]
            tank_depths = [depth for tank in self.cn.tank.values() for depth in [tank.depth1, tank.depth2, tank.depth3, tank.depth4]]
        return buffer_depths + tank_depths + [
            H0CN.hp_ewt, H0CN.hp_lwt, H0CN.dist_swt, H0CN.dist_rwt, 
            H0CN.buffer_cold_pipe, H0CN.buffer_hot_pipe, H0CN.store_cold_pipe, H0CN.store_hot_pipe
        ]
        
    def time_to_trigger_house_cold_onpeak(self) -> bool:
        """
        Logic for triggering HouseColdOnpeak (and moving to top state UsingBakupOnpeak).

        In winter, this means:1) its onpeak  2) house is cold 3) buffer is really empty and 4) store is empty

        """
        return self.is_onpeak() and \
            self.is_house_cold() and \
            self.is_buffer_empty(really_empty=True) and \
            self.is_storage_empty()

    def normal_node_state(self) -> str:
        return self.state

    def is_initializing(self) -> bool:
        return self.state == HaWinterState.Initializing

    def normal_node_goes_dormant(self) -> None:
        """GoDormant: Any -> Dormant for self.state"""
        if self.state != HaWinterState.Dormant:
            self.trigger_normal_event(HaWinterEvent.GoDormant)

    def normal_node_wakes_up(self) -> None:
        """WakeUp: Dormant -> Initializing for self.state"""
        if self.state == HaWinterState.Dormant:
            self.trigger_normal_event(HaWinterEvent.WakeUp)
            self.time_since_blind = None
            self.engage_brain()

    def engage_brain(self) -> None:
        """
        Manages the logic for the Normal top state, (ie. self.state)
        """
        if self.top_state != HomeAloneTopState.Normal:
            self.log(f"brain is only for Normal top state, not {self.top_state}")
            return

        if self.state == HaWinterState.Dormant:
            self.alert("BadHomeAloneState", "TopState Normal, state Dormant!")
            self.trigger_normal_event(HaWinterEvent.WakeUp)
        
        if not self.actuators_initialized:
            self.initialize_actuators()

        previous_state = self.state

        if self.is_onpeak():
            self.storage_declared_ready = False
            self.full_storage_energy = None

        time_now = datetime.now(self.timezone)
        if ((time_now.hour==6 or time_now.hour==16) and time_now.minute>57) or self.zone_setpoints=={}:
            self.get_zone_setpoints()
        
        if not (self.heating_forecast_available() and self.temperatures_available()):
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
            if self.state==HaWinterState.Initializing:
                if self.temperatures_available():
                    if self.is_onpeak():
                        if self.is_buffer_empty():
                            if self.is_storage_colder_than_buffer():
                                self.trigger_normal_event(HaWinterEvent.OnPeakStorageColderThanBuffer)
                            else:
                                self.trigger_normal_event(HaWinterEvent.OnPeakBufferEmpty)
                        else:
                            self.trigger_normal_event(HaWinterEvent.OnPeakBufferFull)
                    else:
                        if self.is_buffer_empty():
                            self.trigger_normal_event(HaWinterEvent.OffPeakBufferEmpty)
                        else:
                            if self.is_storage_ready():
                                self.trigger_normal_event(HaWinterEvent.OffPeakBufferFullStorageReady)
                            else:
                                self.trigger_normal_event(HaWinterEvent.OffPeakBufferFullStorageNotReady)

            elif self.state==HaWinterState.HpOnStoreOff:
                if self.is_onpeak():
                    self.trigger_normal_event(HaWinterEvent.OnPeakStart)
                elif self.is_buffer_full():
                    if self.is_storage_ready():
                        self.trigger_normal_event(HaWinterEvent.OffPeakBufferFullStorageReady)
                    else:
                        usable = self.data.latest_channel_values[H0CN.usable_energy] / 1000
                        required = self.data.latest_channel_values[H0CN.required_energy] / 1000
                        if usable < required:
                            self.trigger_normal_event(HaWinterEvent.OffPeakBufferFullStorageNotReady)
                        else:
                            self.trigger_normal_event(HaWinterEvent.OffPeakBufferFullStorageReady)
                
            elif self.state==HaWinterState.HpOnStoreCharge:
                if self.is_onpeak():
                    self.trigger_normal_event(HaWinterEvent.OnPeakStart)
                elif self.is_buffer_empty():
                    self.trigger_normal_event(HaWinterEvent.OffPeakBufferEmpty)
                elif self.is_storage_ready():
                    self.trigger_normal_event(HaWinterEvent.OffPeakStorageReady)
                
            elif self.state==HaWinterState.HpOffStoreOff:
                if self.is_onpeak():
                    if self.is_buffer_empty() and not self.is_storage_colder_than_buffer():
                        self.trigger_normal_event(HaWinterEvent.OnPeakBufferEmpty)
                else:
                    if self.is_buffer_empty():
                        self.trigger_normal_event(HaWinterEvent.OffPeakBufferEmpty)
                    elif not self.is_storage_ready():
                        usable = self.data.latest_channel_values[H0CN.usable_energy] / 1000
                        required = self.data.latest_channel_values[H0CN.required_energy] / 1000
                        if self.storage_declared_ready:
                            if self.full_storage_energy is None:
                                if usable > 0.9*required:
                                    self.log("The storage was already declared ready during this off-peak period")
                                else:
                                    self.trigger_normal_event(HaWinterEvent.OffPeakStorageNotReady)
                            else:
                                if usable > 0.9*self.full_storage_energy:
                                    self.log("The storage was already declared full during this off-peak period")
                                else:
                                    self.trigger_normal_event(HaWinterEvent.OffPeakStorageNotReady)
                        else:
                            self.trigger_normal_event(HaWinterEvent.OffPeakStorageNotReady)

            elif self.state==HaWinterState.HpOffStoreDischarge:
                if not self.is_onpeak():
                    self.trigger_normal_event(HaWinterEvent.OffPeakStart)
                elif self.is_buffer_full():
                    self.trigger_normal_event(HaWinterEvent.OnPeakBufferFull)
                elif self.is_storage_colder_than_buffer():
                    self.trigger_normal_event(HaWinterEvent.OnPeakStorageColderThanBuffer)

        if (self.state != previous_state) and self.top_state == HomeAloneTopState.Normal:
            self.update_relays(previous_state)

    def update_relays(self, previous_state) -> None:
        if self.top_state != HomeAloneTopState.Normal:
            raise Exception("Can not go into update_relays if top state is not Normal")
        if self.state == HaWinterState.Dormant or self.state == HaWinterState.Initializing:
            return
        if "HpOn" not in previous_state and "HpOn" in self.state:
            self.turn_on_HP(from_node=self.normal_node)
        if "HpOff" not in previous_state and "HpOff" in self.state:
            self.turn_off_HP(from_node=self.normal_node)
        if "StoreDischarge" in self.state:
            self.turn_on_store_pump(from_node=self.normal_node)
        else:
            self.turn_off_store_pump(from_node=self.normal_node)         
        if "StoreCharge" in self.state:
            self.valved_to_charge_store(from_node=self.normal_node)
        else:
            self.valved_to_discharge_store(from_node=self.normal_node)

    def fill_missing_store_temps(self):
        if list(self.latest_temperatures.keys()) == self.temperature_channel_names:
            return
        all_store_layers = sorted([x for x in self.temperature_channel_names if 'tank' in x])
        for layer in all_store_layers:
            if (layer not in self.latest_temperatures 
            or self.to_fahrenheit(self.latest_temperatures[layer]/1000) < 70
            or self.to_fahrenheit(self.latest_temperatures[layer]/1000) > 200):
                self.latest_temperatures[layer] = None
        if H0CN.store_cold_pipe in self.latest_temperatures:
            value_below = self.latest_temperatures[H0CN.store_cold_pipe]
        else:
            value_below = 0
        for layer in sorted(all_store_layers, reverse=True):
            if self.latest_temperatures[layer] is None:
                self.latest_temperatures[layer] = value_below
            value_below = self.latest_temperatures[layer]  
        self.latest_temperatures = {k:self.latest_temperatures[k] for k in sorted(self.latest_temperatures)}

    def is_buffer_empty(self, really_empty=False) -> bool:
        if H0CN.buffer.depth1 in self.latest_temperatures:
            if really_empty or cast(PicoTankModuleComponentGt, self.layout.nodes['buffer']).PicoHwUid:
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
        elif H0CN.buffer.depth3 in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer.depth3
        elif H0CN.buffer_cold_pipe in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer_cold_pipe
        elif "StoreDischarge" in self.state and H0CN.store_cold_pipe in self.latest_temperatures:
            buffer_full_ch = H0CN.store_cold_pipe
        elif H0CN.hp_ewt in self.latest_temperatures:
            buffer_full_ch =  H0CN.hp_ewt
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

    def is_storage_ready(self) -> bool:
        total_usable_kwh = self.data.latest_channel_values[H0CN.usable_energy] / 1000
        required_storage = self.data.latest_channel_values[H0CN.required_energy] / 1000

        if total_usable_kwh >= required_storage:
            self.log(f"Storage ready (usable {round(total_usable_kwh,1)} kWh >= required {round(required_storage,1)} kWh)")
            self.storage_declared_ready = True
            return True
        else:
            if H0N.store_cold_pipe in self.latest_temperatures:
                self.log(f"Store cold pipe: {round(self.to_fahrenheit(self.latest_temperatures[H0N.store_cold_pipe]/1000),1)} F")
                if self.to_fahrenheit(self.latest_temperatures[H0N.store_cold_pipe]/1000) > self.params.MaxEwtF:
                    self.log(f"The storage is not ready, but the bottom is above the maximum EWT ({self.params.MaxEwtF} F).")
                    self.log("The storage will therefore be considered ready, as we cannot charge it further.")
                    self.full_storage_energy = total_usable_kwh
                    self.storage_declared_ready = True
                    return True
            self.log(f"Storage not ready (usable {round(total_usable_kwh,1)} kWh < required {round(required_storage,1)} kWh)")
            return False
        
    def is_storage_empty(self):
        if not self.is_simulated:
            total_usable_kwh = self.data.latest_channel_values[H0CN.usable_energy] / 1000
        else:
            total_usable_kwh = 0
        if total_usable_kwh < 0.2:
            self.log("Storage is empty")
            return True
        else:
            self.log("Storage is not empty")
            return False

    def is_storage_colder_than_buffer(self) -> bool:
        if H0CN.buffer.depth1 in self.latest_temperatures:
            buffer_top = H0CN.buffer.depth1
        elif H0CN.buffer.depth2 in self.latest_temperatures:
            buffer_top = H0CN.buffer.depth2
        elif H0CN.buffer.depth3 in self.latest_temperatures:
            buffer_top = H0CN.buffer.depth3
        elif H0CN.buffer.depth4 in self.latest_temperatures:
            buffer_top = H0CN.buffer.depth4
        elif H0CN.buffer_cold_pipe in self.latest_temperatures:
            buffer_top = H0CN.buffer_cold_pipe
        else:
            self.alert("store_v_buffer_fail", "It is impossible to know if the top of the buffer is warmer than the top of the storage!")
            return False
        if self.cn.tank[1].depth1 in self.latest_temperatures:
            tank_top = self.cn.tank[1].depth1
        elif H0CN.store_hot_pipe in self.latest_temperatures:
            tank_top = H0CN.store_hot_pipe
        elif H0CN.buffer_hot_pipe in self.latest_temperatures:
            tank_top = H0CN.buffer_hot_pipe
        else:
            self.alert("store_v_buffer_fail", "It is impossible to know if the top of the storage is warmer than the top of the buffer!")
            return False
        if self.latest_temperatures[buffer_top] > self.latest_temperatures[tank_top] + 3:
            self.log("Storage top colder than buffer top")
            return True
        else:
            print("Storage top warmer than buffer top")
            return False
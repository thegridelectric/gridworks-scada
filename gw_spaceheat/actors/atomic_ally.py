import asyncio
import time
import datetime
import uuid
from enum import auto
from typing import cast, List, Sequence, Optional

import pytz
from data_classes.house_0_names import H0CN, H0N
from gw.enums import GwStrEnum
from gwproactor import MonitoredName, ServicesInterface
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.data_classes.components.dfr_component import DfrComponent

from gwproto.enums import ActorClass, FsmReportType, RelayClosedOrOpen
from gwproto.named_types import (AnalogDispatch, FsmAtomicReport, FsmFullReport)
from result import Ok, Result
from transitions import Machine

from actors.scada_actor import ScadaActor
from actors.scada_data import ScadaData
from enums import AtomicAllyState, HomeAloneStrategy, LogLevel
from named_types import (
    AllyGivesUp,  Glitch, GoDormant, Ha1Params, HeatingForecast,
    SingleMachineState, SlowContractHeartbeat, SlowDispatchContract, SuitUp
)


class AtomicAllyEvent(GwStrEnum):
    NoMoreElec = auto()
    ElecBufferFull = auto()
    ElecBufferEmpty = auto()
    NoElecBufferFull = auto()
    NoElecBufferEmpty = auto()
    WakeUp = auto()
    GoDormant = auto()
    StartHackOil = auto()
    StopHackOil = auto()

    @classmethod
    def enum_name(cls) -> str:
        return "atomic.ally.event"


class AtomicAlly(ScadaActor):
    MAIN_LOOP_SLEEP_SECONDS = 60
    NO_TEMPS_BAIL_MINUTES = 5
    states = [
        AtomicAllyState.Dormant.value,
        AtomicAllyState.Initializing.value,
        AtomicAllyState.HpOnStoreOff.value,
        AtomicAllyState.HpOnStoreCharge.value,
        AtomicAllyState.HpOffStoreOff.value,
        AtomicAllyState.HpOffStoreDischarge.value,
        AtomicAllyState.HpOffOilBoilerTankAquastat.value,

    ]

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

    def __init__(self, name: str, services: ServicesInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False
        # Temperatures
        self.cn: H0CN = self.layout.channel_names
        self.temperature_channel_names = [
            H0CN.buffer.depth1, H0CN.buffer.depth2, H0CN.buffer.depth3, H0CN.buffer.depth4,
            H0CN.hp_ewt, H0CN.hp_lwt, H0CN.dist_swt, H0CN.dist_rwt, 
            H0CN.buffer_cold_pipe, H0CN.buffer_hot_pipe, H0CN.store_cold_pipe, H0CN.store_hot_pipe,
            *(depth for tank in self.cn.tank.values() for depth in [tank.depth1, tank.depth2, tank.depth3, tank.depth4])
        ]
        self.temperatures_available: bool = False
        self.no_temps_since: Optional[int] = None
        # State machine
        self.machine = Machine(
            model=self,
            states=AtomicAlly.states,
            transitions=AtomicAlly.transitions,
            initial=AtomicAllyState.Dormant,
            send_event=True,
        )     
        self.state: AtomicAllyState = AtomicAllyState.Dormant
        self.prev_state: AtomicAllyState = AtomicAllyState.Dormant 
        self.is_simulated = self.settings.is_simulated
        self.log(f"Params: {self.params}")
        self.log(f"self.is_simulated: {self.is_simulated}")
        self.forecasts: Optional[HeatingForecast] = None
        self.storage_declared_full = False
        self.storage_full_since = time.time()
        if H0N.atomic_ally not in self.layout.nodes:
            raise Exception(f"AtomicAlly requires {H0N.atomic_ally} node!!")
    
    @property
    def data(self) -> ScadaData:
        return self._services.data

    @property
    def remaining_watthours(self) -> Optional[int]:
        return self.services.contract_handler.remaining_watthours
    
    @property
    def contract_hb(self) -> Optional[SlowContractHeartbeat]:
        return self.services.contract_handler.latest_scada_hb

    @property
    def params(self) -> Ha1Params:
        return self.data.ha1_params

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="AtomicAlly keepalive")
        )

    def stop(self) -> None:
        self._stop_requested = True
        
    async def join(self):
        ...

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        from_node = self.layout.node(message.Header.Src, None)
        match message.Payload:
            case GoDormant():
                if self.state != AtomicAllyState.Dormant:
                    # GoDormant: AnyOther -> Dormant ...
                    self.trigger_event(AtomicAllyEvent.GoDormant)
                    self.log("Going dormant")
            case HeatingForecast():
                self.log("Received forecast")
                self.forecasts = message.Payload
            case SlowDispatchContract(): # WakeUp
                try:
                    self.process_slow_dispatch_contract(from_node, message.Payload)
                except Exception as e:
                    self.log(f"Trouble with process_slow_dispatch_contract: {e}")
        return Ok(True)
    
    def process_slow_dispatch_contract(self, from_node, contract: SlowDispatchContract) -> None:
        """ Used to start new contracts and/or to wake up"""
        self.log("Processing SlowDispatchContract!")
        if from_node != self.primary_scada:
            raise Exception("contract should come from scada!")
        
        if self.layout.ha_strategy in [HomeAloneStrategy.Summer]:
            self.log(f"Cannot wake up - in summer mode")
            self._send_to(
                self.primary_scada,
                AllyGivesUp(Reason="In Summer Mode ... does not enter DispatchContracts"))
            return

        if not self.forecasts:
            self.log("Cannot Wake up - missing forecasts!")
            self._send_to(
                self.primary_scada,
                AllyGivesUp(Reason="Missing forecasts required for operation"))
            return
        if self.state == AtomicAllyState.Dormant:
            self.log("Got a slow dispatch contract ... waking up")
            self.wake_up()
        if contract.OilBoilerOn:
            if self.state != AtomicAllyState.HpOffOilBoilerTankAquastat:
                self.log("SlowDispatchContract: OilBoilerOn")
                self.trigger_event(AtomicAllyEvent.StartHackOil)
            else:
                self.log(f"Received contract w OilBoilerOn. Already in {self.state} so ignoring")
        else:
            if self.state == AtomicAllyState.HpOffOilBoilerTankAquastat:
                self.trigger_event(AtomicAllyEvent.StopHackOil) # will go to initializing
            self.engage_brain()
    
    def trigger_event(self, event: AtomicAllyEvent) -> None:
        now_ms = int(time.time() * 1000)
        self.prev_state = self.state
        self.trigger(event)
        self.log(f"{event}: {self.prev_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=AtomicAllyState.enum_name(),
                State=self.state,
                UnixMs=now_ms,
            ),
        )

        # Could update this to receive back reports from the relays and
        # add them to the report.
        trigger_id = str(uuid.uuid4())
        self._send_to(
            self.primary_scada,
            FsmFullReport(
                FromName=self.name,
                TriggerId=trigger_id,
                AtomicList=[
                    FsmAtomicReport(
                        MachineHandle=self.node.handle,
                        StateEnum=AtomicAllyState.enum_name(),
                        ReportType=FsmReportType.Event,
                        EventEnum=AtomicAllyEvent.enum_name(),
                        Event=event,
                        FromState=self.prev_state,
                        ToState=self.state,
                        UnixTimeMs=now_ms,
                        TriggerId=trigger_id,
                    )
                ],
            ),
        )
        self.update_relays()

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.MAIN_LOOP_SLEEP_SECONDS * 2.1)]

    def wake_up(self) -> None:
        """
          - If temperatures are not available, logs no_temp_since (to kick out in 5 minutes)
          - Sends SuitUp back to Scada (so Scada knows it is taking control)
          - Sets state (and then initializes actuators and sets command tree if needed)
           - WakeUpDormant -> Initializing (wake_up)

        """
        self.log("Waking up")

        self.get_latest_temperatures()
        if not self.temperatures_available:
            self.no_temps_since = int(time.time())
            self.log("Temperatures not available. Won't turn on hp until they are. Will bail in 5 if still not available")
        
        self._send_to(self.primary_scada, SuitUp(ToNode=H0N.primary_scada, FromNode=self.name))

        #  Dormant -> Initializing
        self.trigger_event(AtomicAllyEvent.WakeUp) # Dormant -> Initializing
        self.initialize_actuators()

    def engage_brain(self) -> None:
        self.log(f"State: {self.state}")
        if self.state not in [AtomicAllyState.Dormant, 
                              AtomicAllyState.HpOffOilBoilerTankAquastat]:
            self.get_latest_temperatures()

            if self.state == AtomicAllyState.Initializing:
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
            elif self.state == AtomicAllyState.HpOnStoreOff:
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
            elif self.state == AtomicAllyState.HpOnStoreCharge:
                if self.hp_should_be_off():
                    self.trigger_event(AtomicAllyEvent.NoMoreElec)
                elif self.is_buffer_empty() or self.is_storage_full():
                    self.trigger_event(AtomicAllyEvent.ElecBufferEmpty)

            # 3
            elif self.state == AtomicAllyState.HpOffStoreOff:
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
            elif self.state == AtomicAllyState.HpOffStoreDischarge:
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

    async def main(self):
        await asyncio.sleep(2)
        while not self._stop_requested:

            self._send(PatInternalWatchdogMessage(src=self.name))
            self.engage_brain()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    def update_relays(self) -> None:
        self.log(f"update_relays with previous_state {self.prev_state} and state {self.state}")
        if self.state == AtomicAllyState.Dormant:
            return
        if self.state == AtomicAllyState.Initializing:
            if self.hp_should_be_off():
                self.turn_off_HP()
            return


        if self.prev_state == AtomicAllyState.HpOffOilBoilerTankAquastat:
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
        if self.state == AtomicAllyState.HpOffOilBoilerTankAquastat.value:
            self.hp_failsafe_switch_to_aquastat()
            self.aquastat_ctrl_switch_to_boiler()
        else:
            self.hp_failsafe_switch_to_scada()
            self.aquastat_ctrl_switch_to_scada()

    def fill_missing_store_temps(self):
        all_store_layers = sorted([x for x in self.temperature_channel_names if 'tank' in x])
        for layer in all_store_layers:
            if (layer not in self.latest_temperatures 
            or self.latest_temperatures[layer] < 60
            or self.latest_temperatures[layer] > 200):
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

    def get_latest_temperatures(self):
        if not self.is_simulated:
            temp = {
                x: self.data.latest_channel_values[x] 
                for x in self.temperature_channel_names
                if x in self.data.latest_channel_values
                and self.data.latest_channel_values[x] is not None
                }
            self.latest_temperatures = temp.copy()
        else:
            self.log("IN SIMULATION - set all temperatures to 60 degC")
            self.latest_temperatures = {}
            for channel_name in self.temperature_channel_names:
                self.latest_temperatures[channel_name] = 60 * 1000
        for channel in self.latest_temperatures:
            if self.latest_temperatures[channel] is not None:
                self.latest_temperatures[channel] = self.to_fahrenheit(self.latest_temperatures[channel]/1000)
        if list(self.latest_temperatures.keys()) == self.temperature_channel_names:
            self.temperatures_available = True
            print('Temperatures available')
        else:
            self.temperatures_available = False
            print('Some temperatures are missing')
            all_buffer = [x for x in self.temperature_channel_names if 'buffer-depth' in x]
            available_buffer = [x for x in list(self.latest_temperatures.keys()) if 'buffer-depth' in x]
            if all_buffer == available_buffer:
                print("All the buffer temperatures are available")
                self.fill_missing_store_temps()
                print("Successfully filled in the missing storage temperatures.")
                self.temperatures_available = True
        total_usable_kwh = self.data.latest_channel_values[H0CN.usable_energy]
        required_storage = self.data.latest_channel_values[H0CN.required_energy]
        if total_usable_kwh is None or required_storage is None:
            self.temperatures_available = False

    def initialize_actuators(self):
        """
          - de-energizes all non-critical relays directly reporting to aa
          - sets 0-10V outputs to defaults

        """
        my_relays =  {
            relay
            for relay in self.my_actuators()
            if relay.ActorClass == ActorClass.Relay and self.the_boss_of(relay) == self.node
        }

        target_relays: List[ShNode] = list(my_relays - {
                self.store_charge_discharge_relay, # keep as it was
                self.hp_failsafe_relay,
                self.hp_scada_ops_relay, # keep as it was unless on peak
                self.aquastat_control_relay, # de-energized turns on oil boiler - only go here if scada is dead!
                self.hp_loop_on_off, # de-energized keeps telling hp loop valve to change - only go here if scada is dead!
            }
        )
        target_relays.sort(key=lambda x: x.Name)
        self.log("Initializing actuators")
        self.log("de-energizing most relays")
        for relay in target_relays:
            try:
                self.de_energize(relay)
            except Exception as e:
                self.log(f"Trouble de energizing {relay}")

        self.log("Taking care of relays with default energized positions")
        self.hp_failsafe_switch_to_scada()
        self.aquastat_ctrl_switch_to_scada()
        self.sieg_valve_dormant()
        if self.hp_should_be_off():
            self.turn_off_HP()
        try:
            self.set_010_defaults()
        except ValueError as e:
            self.log(f"Trouble with set_010_defaults: {e}")

    def set_010_defaults(self) -> None:
        """
        Set 0-10 defaults for ZeroTen outputters that are direct reports
        """
        dfr_component = cast(DfrComponent, self.layout.node(H0N.zero_ten_out_multiplexer).component)
        h_normal_010s = {
            node
            for node in self.my_actuators()
            if node.ActorClass == ActorClass.ZeroTenOutputer and
            self.the_boss_of(node) == self.node
        }
        for dfr_node in h_normal_010s:
            dfr_config = next(
                    config
                    for config in dfr_component.gt.ConfigList
                    if config.ChannelName == dfr_node.name
                )
            self._send_to(
                dst=dfr_node,
                payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    FromHandle=self.node.handle,
                    ToHandle=dfr_node.handle,
                    AboutName=dfr_node.Name,
                    Value=dfr_config.InitialVoltsTimes100,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                )
            )
            self.log(f"Just set {dfr_node.handle} to {dfr_config.InitialVoltsTimes100} from {self.node.handle} ")            

    def hp_should_be_off(self) -> bool:
        if self.remaining_watthours:
            if self.remaining_watthours > 0:
                return False
        
        if self.hp_scada_ops_relay.name in self.data.latest_machine_state.keys():
            scada_relay_state = self.data.latest_machine_state[self.hp_scada_ops_relay.name].State
            
            if scada_relay_state == RelayClosedOrOpen.RelayClosed:
                # If the relay is closed and there is no contract, keep it closed
                if self.contract_hb is None:
                    return False
                # If the relay is closed and in the last 5 minutes of >= 30 minute contract,
                #  keep it closed
                elif self.contract_hb.Contract.DurationMinutes >= 30:  
                    c = self.contract_hb.Contract
                    last_5 = c.StartS + (c.DurationMinutes - 5)*60  
                    if time.time() > last_5:
                        return False
        return True
    
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
        if self.forecasts is None:
            self.alert(summary="buffer_empty_fail", details="Impossible without forecasts")
            return False
        max_rswt_next_3hours = max(self.forecasts.RswtF[:3])
        max_deltaT_rswt_next_3_hours = max(self.forecasts.RswtDeltaTF[:3])
        min_buffer = round(max_rswt_next_3hours - max_deltaT_rswt_next_3_hours,1)
        buffer_empty_ch_temp = round(self.latest_temperatures[buffer_empty_ch],1)
        if buffer_empty_ch_temp < min_buffer:
            self.log(f"Buffer empty ({buffer_empty_ch}: {buffer_empty_ch_temp} < {min_buffer} F)")
            return True
        else:
            self.log(f"Buffer not empty ({buffer_empty_ch}: {buffer_empty_ch_temp} >= {min_buffer} F)")
            return False            
    
    def is_buffer_full(self, really_full=False) -> bool:
        if H0CN.buffer.depth4 in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer.depth4
        elif H0CN.buffer_cold_pipe in self.latest_temperatures:
            buffer_full_ch = H0CN.buffer_cold_pipe
        elif "StoreDischarge" in self.state and H0CN.store_cold_pipe in self.latest_temperatures:
            buffer_full_ch = H0CN.store_cold_pipe
        elif 'hp-ewt' in self.latest_temperatures:
            buffer_full_ch = 'hp-ewt'
        else:
            self.alert(summary="buffer_full_fail", details="Impossible to know if the buffer is full!")
            return False
        if self.forecasts is None:
            self.alert(summary="buffer_full_fail", details="Impossible without forecasts")
            return False
        max_buffer = round(max(self.forecasts.RswtF[:3]),1)
        buffer_full_ch_temp = round(self.latest_temperatures[buffer_full_ch],1)

        if really_full:
            if H0CN.buffer_cold_pipe in self.latest_temperatures:
                buffer_full_ch_temp = round(max(self.latest_temperatures[H0CN.buffer_cold_pipe], self.latest_temperatures[buffer_full_ch]),1)
            max_buffer = self.params.MaxEwtF
            if buffer_full_ch_temp > max_buffer:
                self.log(f"Buffer cannot be charged more ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F)")
                return True
            else:
                self.log(f"Buffer can be charged more ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F)")
                return False
            
        if buffer_full_ch_temp > max_buffer:
            self.log(f"Buffer full ({buffer_full_ch}: {buffer_full_ch_temp} > {max_buffer} F)")
            return True
        else:
            self.log(f"Buffer not full ({buffer_full_ch}: {buffer_full_ch_temp} <= {max_buffer} F)")
            return False
        
    def is_storage_full(self) -> bool:
        if self.storage_declared_full and time.time() - self.storage_full_since < 15*60:
            self.log(f"Storage was declared full {round((time.time() - self.storage_full_since)/60)} minutes ago")
            return True
        elif self.latest_temperatures[H0N.store_cold_pipe] > self.params.MaxEwtF: 
            self.log(f"Storage is full (store-cold-pipe > {self.params.MaxEwtF} F).")
            self.storage_declared_full = True
            self.storage_full_since = time.time()
            return True
        else:
            self.log(f"Storage is not full (store-cold-pipe <= {self.params.MaxEwtF} F).")
            self.storage_declared_full = False
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
            self.alert(summary="store_v_buffer_fail", details="It is impossible to know if the top of the buffer is warmer than the top of the storage!")
            return False
        if self.cn.tank[1].depth1 in self.latest_temperatures:
            tank_top = self.cn.tank[1].depth1
        elif H0CN.store_hot_pipe in self.latest_temperatures:
            tank_top = H0CN.store_hot_pipe
        elif H0CN.buffer_hot_pipe in self.latest_temperatures:
            tank_top = H0CN.buffer_hot_pipe
        else:
            self.alert(summary="store_v_buffer_fail", details="It is impossible to know if the top of the storage is warmer than the top of the buffer!")
            return False
        if self.latest_temperatures[buffer_top] > self.latest_temperatures[tank_top] + 3:
            self.log("Storage top colder than buffer top")
            return True
        else:
            print("Storage top warmer than buffer top")
            return False
        
    def to_fahrenheit(self, t:float) -> float:
        return t*9/5+32

    def alert(self, summary: str, details: str) -> None:
        msg =Glitch(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            Node=self.node.Name,
            Type=LogLevel.Critical,
            Summary=summary,
            Details=details
        )
        self._send_to(self.atn, msg)
        self.log(f"Glitch: {summary}")
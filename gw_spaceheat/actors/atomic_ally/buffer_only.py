import asyncio
import time
import uuid
from typing import cast, List, Sequence, Optional

from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.sh_node import ShNode
from gwproto.data_classes.components.dfr_component import DfrComponent

from gwproto.enums import ActorClass, FsmReportType, RelayClosedOrOpen
from gwsproto.enums import AaBufferOnlyState, AaBufferOnlyEvent
from gwproto.named_types import (
    AnalogDispatch, FsmAtomicReport, FsmFullReport,
    SyncedReadings,
)
from result import Ok, Result
from transitions import Machine

from actors.scada_actor import ScadaActor
from scada_app_interface import ScadaAppInterface
from gwsproto.enums import HomeAloneStrategy
from gwsproto.named_types import (
    AllyGivesUp, GoDormant, Ha1Params,
    SingleMachineState, SlowContractHeartbeat, SlowDispatchContract, SuitUp
)


class BufferOnlyAtomicAlly(ScadaActor):
    MAIN_LOOP_SLEEP_SECONDS = 60
    NO_TEMPS_BAIL_MINUTES = 5
    states = AaBufferOnlyState.values()
    # Uses AaBufferOnlyEvent as transitions
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

    def __init__(self, name: str, services: ScadaAppInterface):
        super().__init__(name, services)
        self._stop_requested: bool = False

        self.no_temps_since: Optional[int] = None
        # State machine
        self.machine = Machine(
            model=self,
            states=BufferOnlyAtomicAlly.states,
            transitions=BufferOnlyAtomicAlly.transitions,
            initial=AaBufferOnlyState.Dormant,
            send_event=True,
        )     
        self.state: AaBufferOnlyState = AaBufferOnlyState.Dormant
        self.prev_state: AaBufferOnlyState = AaBufferOnlyState.Dormant 
        self.log(f"Params: {self.params}")
        self.time_buffer_full = 0
        if H0N.atomic_ally not in self.layout.nodes:
            raise Exception(f"AtomicAlly requires {H0N.atomic_ally} node!!")

    @property
    def remaining_watthours(self) -> Optional[int]:
        return self.services.scada.contract_handler.remaining_watthours
    
    @property
    def contract_hb(self) -> Optional[SlowContractHeartbeat]:
        return self.services.scada.contract_handler.latest_scada_hb

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
                if self.state != AaBufferOnlyState.Dormant:
                    # GoDormant: AnyOther -> Dormant ...
                    self.trigger_event(AaBufferOnlyEvent.GoDormant)
                    self.log("Going dormant")
            case SlowDispatchContract(): # WakeUp
                try:
                    self.process_slow_dispatch_contract(from_node, message.Payload)
                except Exception as e:
                    self.log(f"Trouble with process_slow_dispatch_contract: {e}")
            case SyncedReadings():
                self.log("Received buffer readings")
                # buffer temps are in data.latest_channel_values but not
                # yet in self.latest_temperatures_f
                if self.state == AaBufferOnlyState.Initializing and self.heating_forecast:
                    self.reconcile_tank_temperatures()
                    self.engage_brain()
        return Ok(True)
    
    def process_slow_dispatch_contract(self, from_node, contract: SlowDispatchContract) -> None:
        """ Used to start new contracts and/or to wake up"""
        self.log("Processing SlowDispatchContract!")
        if from_node != self.primary_scada:
            raise Exception("contract should come from scada!")
        
        if self.layout.ha_strategy in [HomeAloneStrategy.Summer]:
            self.log("Cannot wake up - in summer mode")
            self._send_to(
                self.primary_scada,
                AllyGivesUp(Reason="In Summer Mode ... does not enter DispatchContracts"))
            return

        if not self.heating_forecast:
            self.log("Cannot Wake up - missing forecasts!")
            self._send_to(
                self.primary_scada,
                AllyGivesUp(Reason="Missing forecasts required for operation"))
            return
        if self.state == AaBufferOnlyState.Dormant:
            self.log("Got a slow dispatch contract ... waking up")
            self.wake_up()
        if contract.OilBoilerOn:
            if self.state != AaBufferOnlyState.HpOffOilBoilerTankAquastat:
                self.log("SlowDispatchContract: OilBoilerOn")
                self.trigger_event(AaBufferOnlyEvent.StartHackOil)
            else:
                self.log(f"Received contract w OilBoilerOn. Already in {self.state} so ignoring")
        else:
            if self.state == AaBufferOnlyState.HpOffOilBoilerTankAquastat:
                self.trigger_event(AaBufferOnlyEvent.StopHackOil) # will go to initializing
            self.engage_brain()
    
    def trigger_event(self, event: AaBufferOnlyEvent) -> None:
        now_ms = int(time.time() * 1000)
        self.prev_state = self.state
        self.trigger(event)
        self.log(f"{event}: {self.prev_state} -> {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=AaBufferOnlyState.enum_name(),
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
                        StateEnum=AaBufferOnlyState.enum_name(),
                        ReportType=FsmReportType.Event,
                        EventEnum=AaBufferOnlyEvent.enum_name(),
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

        self.reconcile_tank_temperatures()
        if not self.buffer_temps_available:
            self.no_temps_since = int(time.time())
            self.log("Temperatures not available. Won't turn on hp until they are. Will bail in 5 if still not available")
        
        self._send_to(self.primary_scada, SuitUp(ToNode=H0N.primary_scada, FromNode=self.name))

        #  Dormant -> Initializing
        self.trigger_event(AaBufferOnlyEvent.WakeUp) # Dormant -> Initializing
        self.initialize_actuators()

    def engage_brain(self) -> None:
        self.log(f"State: {self.state}")
        if self.state not in [AaBufferOnlyState.Dormant, 
                              AaBufferOnlyState.HpOffOilBoilerTankAquastat]:
            self.reconcile_tank_temperatures()

            if self.state == AaBufferOnlyState.Initializing:
                if self.buffer_temps_available  and self.data.channel_has_value(H0CN.required_energy):
                    self.no_temps_since = None
                    if self.hp_should_be_off():
                        self.trigger_event(AaBufferOnlyEvent.NoMoreElec)
                    elif self.is_buffer_charge_limited():
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
                elif self.is_buffer_charge_limited():
                    self.log("Buffer is as full as can be")
                    self.time_buffer_full = int(time.time())
                    self.trigger_event(AaBufferOnlyEvent.BufferFull)
                    # TODO: send message to ATN saying the EnergyInstruction will be violated

            # 2
            elif self.state == AaBufferOnlyState.HpOff:
                if not self.hp_should_be_off() and time.time()-self.time_buffer_full>15*60:
                    self.trigger_event(AaBufferOnlyEvent.ChargeBuffer)

    async def main(self):
        await asyncio.sleep(2)
        while not self._stop_requested:

            self._send(PatInternalWatchdogMessage(src=self.name))
            self.engage_brain()
            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

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


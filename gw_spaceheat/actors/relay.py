"""Implements Relay Actors"""
import asyncio
import time
from typing import Dict, List, cast, Sequence, Optional

from gw.enums import GwStrEnum
from gwproto.message import Message
from gwproto.data_classes.data_channel import DataChannel
from gwproactor import  MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto.data_classes.components.i2c_multichannel_dt_relay_component import (
    I2cMultichannelDtRelayComponent,
)
from gwsproto.data_classes.house_0_names import H0N
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import (
    AquastatControl,
    ChangeAquastatControl,
    ChangeHeatPumpControl,
    ChangePrimaryPumpControl,
    ChangeRelayPin,
    ChangeRelayState,
    ChangeStoreFlowRelay,
    ChangeHeatcallSource,
    FsmReportType,
    HeatPumpControl,
    MakeModel,
    PrimaryPumpControl,
    RelayClosedOrOpen,
    RelayWiringConfig,
    StoreFlowRelay,
    HeatcallSource,

)

from gwproto.named_types import FsmAtomicReport, FsmFullReport
from result import Err, Ok, Result
from transitions import Machine
from gwsproto.data_classes.house_0_names import House0RelayIdx
from actors.scada_actor import ScadaActor
from scada_app_interface import ScadaAppInterface
from gwsproto.enums import LogLevel, ChangeKeepSend, HpLoopKeepSend
from gwsproto.named_types import FsmEvent, Glitch, SingleMachineState

class Relay(ScadaActor):
    STATE_REPORT_S = 300
    node: ShNode
    component: I2cMultichannelDtRelayComponent
    wiring_config: RelayWiringConfig
    my_state_enum: GwStrEnum
    my_event_enum: GwStrEnum
    reports_by_trigger: Dict[str, List[FsmAtomicReport]]
    boss_by_trigger: Dict[str, ShNode]
    energized_state: str
    de_energized_state: str

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)
        self.component = cast(I2cMultichannelDtRelayComponent, self.node.component)
        if self.component.cac.MakeModel != MakeModel.KRIDA__DOUBLEEMR16I2CV3:
            raise Exception(
                f"Expected {MakeModel.KRIDA__DOUBLEEMR16I2CV3}, got {self.component.cac}"
            )
        self.relay_actor_config = next(
            (x for x in self.component.gt.ConfigList if x.ActorName == self.node.name),
            None,
        )

        if self.relay_actor_config is None:
            raise Exception(
                f"Relay {self.node.name} not in component {self.component}'s RelayActorConfigList:\n"
                f"{self.component.gt.ConfigList}"
            )

        self.de_energizing_event = self.relay_actor_config.DeEnergizingEvent
        self.relay_multiplexer = self.layout.node(H0N.relay_multiplexer)
        self.reports_by_trigger = {}
        self.boss_by_trigger = {}
        self.my_event_enum = ChangeRelayState.enum_name()
        self.my_state_enum = RelayClosedOrOpen.enum_name()
        self.initialize_fsm()
        self._stop_requested = False

    def my_channel(self) -> DataChannel:
        relay_config = next(
            (
                config
                for config in self.component.gt.ConfigList
                if config.ActorName == self.name
            ),
            None,
        )
        if relay_config is None:
            raise Exception(f"relay {self.name} does not have a state channel!")
        return self.layout.data_channels[relay_config.ChannelName]

    def _process_event_message(
        self, from_name: str, message: FsmEvent
    ) -> Result[bool, BaseException]:
        from_node = self.layout.node(from_name)
        if from_node is None:
            return
        if message.FromHandle != from_node.handle:
            self.log(
                f"from_node {from_node.name} has handle {from_node.handle}, not {message.FromHandle}!"
            )
            return

        if message.ToHandle != self.node.Handle:
            # TODO: turn this into a report?
            self._send_to(self.atn,
                          Glitch(
                              FromGNodeAlias=self.layout.scada_g_node_alias,
                              Node=self.name,
                              Type=LogLevel.Warning,
                              Summary="bad_boss",
                              Details=f"{message.FromHandle} tried to command {self.node.Handle}. Ignoring!"
                          ))
            self.log(f"Handle is {self.node.Handle}; ignoring {message}")
            return

        if message.EventType != self.my_event_enum.enum_name():
            print(f"Not a {self.my_event_enum} event type. Ignoring: {message}")

        orig_state = self.state
        self.trigger(message.EventName)
        if self.state == orig_state:
            ...
            # print(f"{message.EventName} did not change state {self.state}")
        else:
            # state changed
            if message.EventName == self.de_energizing_event:
                relay_pin_event = ChangeRelayPin.DeEnergize
                old_pin_state = "Energized"
                new_pin_state = "DeEnergized"
            else:
                relay_pin_event = ChangeRelayPin.Energize
                old_pin_state = "DeEnergized"
                new_pin_state = "Energized"

            report = FsmAtomicReport(
                MachineHandle=self.node.handle,
                StateEnum=self.my_state_enum.enum_name(),
                ReportType=FsmReportType.Event,
                EventEnum=self.my_event_enum.enum_name(),
                Event=message.EventName,
                FromState=orig_state,
                ToState=self.state,
                UnixTimeMs=message.SendTimeUnixMs,
                TriggerId=message.TriggerId,
            )
            self.reports_by_trigger[message.TriggerId] = [report]
            self.boss_by_trigger[message.TriggerId] = from_node
            now_ms = int(time.time() * 1000)
            # self.log(f"sending {relay_pin_event} to multiplexer")
            #  To actually create an action, send to relay multiplexer
            pin_change_event = FsmEvent(
                FromHandle=self.node.handle,
                ToHandle=self.relay_multiplexer.handle,
                EventType=ChangeRelayPin.enum_name(),
                EventName=relay_pin_event,
                TriggerId=message.TriggerId,
                SendTimeUnixMs=now_ms,
            )
            self._send_to(self.relay_multiplexer, pin_change_event)
            self.reports_by_trigger[message.TriggerId].append(
                FsmAtomicReport(
                    MachineHandle=self.node.handle,
                    StateEnum="relay.pin",
                    ReportType=FsmReportType.Event,
                    EventType=ChangeRelayPin.enum_name(),
                    Event=relay_pin_event,
                    FromState=old_pin_state,
                    ToState=new_pin_state,
                    UnixTimeMs=now_ms,
                    TriggerId=message.TriggerId,
                )
            )
            return Ok()

    def _process_atomic_report(
        self, message: FsmAtomicReport
    ) -> Result[bool, BaseException]:
        if message.TriggerId not in self.reports_by_trigger:
            raise Exception("Unknown trigger!!")
        # i2c multiplexer has gotten our message and acted on it
        # so we report
        self.send_state()
        self.reports_by_trigger[message.TriggerId].append(message)
        boss = self.boss_by_trigger[message.TriggerId]
        # print(f"Sending report to {boss.name}")
        self._send_to(
            boss,
            FsmFullReport(
                FromName=self.name,
                TriggerId=message.TriggerId,
                AtomicList=self.reports_by_trigger[message.TriggerId],
            ),
        )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        if isinstance(message.Payload, FsmEvent):
            return self._process_event_message(
                from_name=message.Header.Src, message=message.Payload
            )
        elif (
            isinstance(message.Payload, FsmAtomicReport)
            and message.Header.Src == self.relay_multiplexer.name
        ):
            return self._process_atomic_report(message.Payload)

        return Err(
            ValueError(
                f"Error. Relay {self.name} receieved unexpected message: {message.Header}"
            )
        )

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.STATE_REPORT_S * 2.1)]

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="relay state reporter")
        )

    async def main(self) -> None:
        await asyncio.sleep(2)
        self.send_state()

        while not self._stop_requested:
            hiccup = 1.2
            sleep_s = max(
                hiccup, self.STATE_REPORT_S - (time.time() % self.STATE_REPORT_S) - 2
            )
            await asyncio.sleep(sleep_s)
            if sleep_s != hiccup:
                self.send_state()
                self._send(PatInternalWatchdogMessage(src=self.name))

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""
        ...

    def send_state(self, now_ms: Optional[int] = None) -> None:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        # self.log(f"[{self.my_channel().Name}] {self.state}")
        self._send_to(
            self.primary_scada,
            SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=self.my_state_enum.enum_name(),
                State=self.state,
                UnixMs=now_ms,
            ),
        )

    def initialize_fsm(self):
        self.my_state_enum = RelayClosedOrOpen
        self.my_event_enum = ChangeRelayState
        self.de_energized_state = "RelayClosed"
        zone_names = self.layout.zone_list
        stat_failsafe_names = []
        stat_ops_names = []
        # TODO: move the below into House0 Hardware Layout validation
        for i in range(len(zone_names)):
            failsafe_idx = House0RelayIdx.base_stat + 2*i
            ops_idx = House0RelayIdx.base_stat + 2*i + 1
            stat_failsafe_names.append(f"relay{failsafe_idx}")
            stat_ops_names.append( f"relay{ops_idx}")
    
        if self.name in {
            H0N.vdc_relay,
            H0N.tstat_common_relay,
            H0N.hp_scada_ops_relay,
            H0N.thermistor_common_relay,
            H0N.store_pump_failsafe,
            H0N.primary_pump_scada_ops,
            H0N.hp_loop_on_off,
        } | set(stat_ops_names):
        
            if self.name in {
                H0N.vdc_relay,
                H0N.tstat_common_relay,
                H0N.hp_scada_ops_relay,
                H0N.thermistor_common_relay,
                H0N.hp_loop_on_off
            }:
                if self.de_energizing_event != ChangeRelayState.CloseRelay:
                    raise Exception(
                        f"Expect CloseRelay as de-energizing event for {self.name}; got {self.de_energizing_event}"
                    )
            else:
                if self.de_energizing_event != ChangeRelayState.OpenRelay:
                    raise Exception(
                        f"Expect OpenRelay as de-energizing event for {self.name}; got {self.de_energizing_event}"
                    )

        elif self.name == H0N.store_charge_discharge_relay:
            self.my_state_enum = StoreFlowRelay
            self.my_event_enum = ChangeStoreFlowRelay
            if self.de_energizing_event != ChangeStoreFlowRelay.DischargeStore:
                raise Exception(
                    f"Expect DischargeStore as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == H0N.hp_failsafe_relay:
            self.my_state_enum = HeatPumpControl
            self.my_event_enum = ChangeHeatPumpControl
            if self.de_energizing_event != ChangeHeatPumpControl.SwitchToTankAquastat:
                raise Exception(
                    f"Expect SwitchToTankAquastat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == H0N.aquastat_ctrl_relay:
            self.my_state_enum = AquastatControl
            self.my_event_enum = ChangeAquastatControl
            if self.de_energizing_event != ChangeAquastatControl.SwitchToBoiler:
                raise Exception(
                    f"Expect SwitchToBoiler as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )

        elif self.name == H0N.primary_pump_failsafe:
            self.my_state_enum = PrimaryPumpControl
            self.my_event_enum = ChangePrimaryPumpControl
            if self.de_energizing_event != ChangePrimaryPumpControl.SwitchToHeatPump:
                raise Exception(
                    f"Expect SwitchToHeatPump as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        elif self.name == H0N.hp_loop_keep_send:
            self.my_state_enum = HpLoopKeepSend
            self.my_event_enum = ChangeKeepSend
            if self.de_energizing_event != ChangeKeepSend.ChangeToKeepLess:
                raise Exception(f"Expect ChangeToSendMore as de-energizing event for {self.name}!")
        elif self.name in stat_failsafe_names:
            self.my_state_enum = HeatcallSource
            self.my_event_enum = ChangeHeatcallSource
            if self.de_energizing_event != ChangeHeatcallSource.SwitchToWallThermostat:
                raise Exception(
                    f"Expect SwitchToWallThermostat as de-energizing event for {self.name}; got {self.de_energizing_event}"
                )
        
        
        self.transitions = [
                {
                    "trigger": self.relay_actor_config.DeEnergizingEvent,
                    "source": self.relay_actor_config.EnergizedState,
                    "dest": self.relay_actor_config.DeEnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.DeEnergizingEvent,
                    "source": self.relay_actor_config.DeEnergizedState,
                    "dest": self.relay_actor_config.DeEnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.EnergizingEvent,
                    "source":self.relay_actor_config.DeEnergizedState,
                    "dest": self.relay_actor_config.EnergizedState,
                },
                {
                    "trigger": self.relay_actor_config.EnergizingEvent,
                    "source": self.relay_actor_config.EnergizedState,
                    "dest":  self.relay_actor_config.EnergizedState,
                },
            ]
        try:
            self.machine = Machine(
                model=self,
                states=self.my_state_enum.values(),
                transitions=self.transitions,
                initial=self.relay_actor_config.DeEnergizedState,
                send_event=True,
            )

        except AttributeError as e:
            self.log(f"PROBLEM with {self.node}!: {e}")

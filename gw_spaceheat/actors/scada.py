"""Scada implementation"""
import os
import random
import asyncio
import enum
import uuid
import threading
import time
import pytz
from typing import Any, Dict, List, Optional, cast

import dotenv
from transitions import Machine
from gwproto.message import Header
from gwproactor.external_watchdog import SystemDWatchdogCommandBuilder
from gwproactor.links.link_settings import LinkSettings
from gwproto import create_message_model

from gwproto.enums import ActorClass

from data_classes.house_0_layout import House0Layout
from gwproto.messages import FsmFullReport
from gwproto.messages import EventBase
from gwproto.message import Message
from gwproto.messages import PowerWatts
from gwproto.messages import SendSnap

from gwproto.named_types import (
    AnalogDispatch, ChannelReadings, MachineStates, SingleReading, SyncedReadings,
)

from gwproto.messages import ReportEvent
from gwproto import MQTTCodec
from result import Ok
from result import Result

from gwproactor import ActorInterface
from actors.scada_data import ScadaData
from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwproto.data_classes.sh_node import ShNode
from gwproactor import QOS

from gwproactor.links import Transition
from gwproactor.message import MQTTReceiptPayload
from gwproactor.persister import TimedRollingFilePersister
from gwproactor.proactor_implementation import Proactor

from actors.subscription_handler import ChannelSubscription, StateMachineSubscription
from actors.home_alone_loader import HomeAlone
from actors.atomic_ally import AtomicAlly
from actors import ContractHandler
from data_classes.house_0_names import H0N
from enums import (AtomicAllyState, ContractStatus, FlowManifoldVariant, HomeAloneTopState, 
                   MainAutoEvent, MainAutoState, TopState)
from named_types import ( ActuatorsReady,
    AdminDispatch, AdminKeepAlive, AdminReleaseControl, AllyGivesUp, ChannelFlatlined,
    Glitch, GoDormant, LayoutLite, NewCommandTree, NoNewContractWarning, ResetHpKeepValue,
    ScadaParams, SendLayout, SetLwtControlParams, SetTargetLwt, SiegLoopEndpointValveAdjustment, 
    SiegTargetTooLow, SingleMachineState,SlowContractHeartbeat, SuitUp, WakeUp,
)

ScadaMessageDecoder = create_message_model(
    "ScadaMessageDecoder",
    [
        "named_types",
        "gwproto.messages",
        "gwproactor.message",
        "actors.message",
    ],
)


class GridworksMQTTCodec(MQTTCodec):
    exp_src: str
    exp_dst: str = H0N.primary_scada

    def __init__(self, hardware_layout: House0Layout):
        self.exp_src = hardware_layout.atn_g_node_alias
        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if src != self.exp_src or dst != self.exp_dst:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: {self.exp_src} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )


class LocalMQTTCodec(MQTTCodec):
    exp_srcs: set[str]
    exp_dst: str

    def __init__(self, *, primary_scada: bool, remote_node_names: set[str]):
        self.primary_scada = primary_scada
        self.exp_srcs = remote_node_names
        if self.primary_scada:
            self.exp_srcs.add(H0N.secondary_scada)
            self.exp_dst = H0N.primary_scada
        else:
            self.exp_srcs.add(H0N.primary_scada)
            self.exp_dst = H0N.secondary_scada

        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        ## Black Magic 🪄
        ##   The message from scada2 contain the *spaceheat name* as
        ##   src, *not* the gnode name, in particular because they might come
        ##   from individual nodes that don't have a gnode.
        ##   Since spaceheat names now contain '-', the encoding/decoding by
        ##   MQTTCodec (done for Rabbit) is not what we we want: "-" ends up as
        ##   "." So we have undo that in this particular case.
        src = src.replace(".", "-")
        ## End Black Magic 🪄

        if dst != self.exp_dst or src not in self.exp_srcs:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: one of {self.exp_srcs} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )


class AdminCodec(MQTTCodec):
    scada_gnode: str

    def __init__(self, scada_gnode: str):
        self.scada_gnode = scada_gnode

        super().__init__(ScadaMessageDecoder)

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if dst != self.scada_gnode or src != H0N.admin:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: one of {H0N.admin} -> {self.scada_gnode}\n"
                f"  got: {src} -> {dst}"
            )


class ScadaCmdDiagnostic(enum.Enum):
    SUCCESS = "Success"
    PAYLOAD_NOT_IMPLEMENTED = "PayloadNotImplemented"
    BAD_FROM_NODE = "BadFromNode"
    DISPATCH_NODE_NOT_RELAY = "DispatchNodeNotRelay"
    UNKNOWN_DISPATCH_NODE = "UnknownDispatchNode"
    IGNORING_HOMEALONE_DISPATCH = "IgnoringHomealoneDispatch"
    IGNORING_ATN_DISPATCH = "IgnoringAtnDispatch"


class Scada(ScadaInterface, Proactor):
    ASYNC_POWER_REPORT_THRESHOLD = 0.05
    DEFAULT_ACTORS_MODULE = "actors"
    ATN_MQTT = "gridworks"
    LOCAL_MQTT = "local"
    ADMIN_MQTT = "admin"

    _data: ScadaData
    _last_report_second: int
    _last_snap_s: int
    _channels_reported: bool
    _admin_timeout_task: Optional[asyncio.Task] = None

    top_states = ["Auto", "Admin"]
    top_transitions = [
        {"trigger": "AdminWakesUp", "source": "Auto", "dest": "Admin"},
        {"trigger": "AdminTimesOut", "source": "Admin", "dest": "Auto"},
        {"trigger": "AdminReleasesControl", "source": "Admin", "dest": "Auto"},
    ]

    main_auto_states = MainAutoState.values()
    main_auto_transitions = [
        {"trigger": "DispatchContractLive", "source": "HomeAlone", "dest": "Atn"},
        {"trigger": "ContractGracePeriodEnds", "source": "Atn", "dest": "HomeAlone"},
        {"trigger": "AtnReleasesControl", "source": "Atn", "dest": "HomeAlone"},
        {"trigger": "AllyGivesUp", "source": "Atn", "dest": "HomeAlone"},
        {"trigger": "AutoGoesDormant", "source": "Atn", "dest": "Dormant"},
        {"trigger": "AutoGoesDormant", "source": "HomeAlone", "dest": "Dormant"},
        {"trigger": "AutoWakesUp", "source": "Dormant", "dest": "HomeAlone"},
    ]

    def __init__(
        self,
        name: str,
        settings: ScadaSettings,
        hardware_layout: House0Layout,
        actor_nodes: Optional[List[ShNode]] = None,
    ):
        if not isinstance(hardware_layout, House0Layout):
            raise Exception("Make sure to pass House0Layout object as hardware_layout!")
        self.is_simulated = False
        self._layout: House0Layout = hardware_layout
        self._data = ScadaData(settings, hardware_layout)
        super().__init__(name=name, settings=settings, hardware_layout=hardware_layout)
        scada2_gnode_name = (
            f"{hardware_layout.scada_g_node_alias}.{H0N.secondary_scada}"
        )
        remote_actor_node_names = {
            node.name
            for node in self._layout.nodes.values()
            if self._layout.parent_node(node) != self._node
            and node != self._node
            and node.has_actor
        } | {scada2_gnode_name.replace(".", "-")}
        self._links.add_mqtt_link(
            LinkSettings(
                client_name=self.LOCAL_MQTT,
                gnode_name=scada2_gnode_name,
                spaceheat_name=H0N.secondary_scada,
                mqtt=self.settings.local_mqtt,
                codec=LocalMQTTCodec(
                    primary_scada=True, remote_node_names=remote_actor_node_names
                ),
                downstream=True,
            )
        )
        self._links.add_mqtt_link(
            LinkSettings(
                client_name=self.ATN_MQTT,
                gnode_name=self._layout.atn_g_node_alias,
                spaceheat_name=H0N.atn,
                mqtt=self.settings.gridworks_mqtt,
                codec=GridworksMQTTCodec(self._layout),
                upstream=True,
            )
        )
        if self.settings.admin.enabled:
            self._links.add_mqtt_link(
                LinkSettings(
                    client_name=self.ADMIN_MQTT,
                    gnode_name=self.settings.admin.name,
                    spaceheat_name=self.settings.admin.name,
                    subscription_name=self.publication_name,
                    mqtt=self.settings.admin,
                    codec=AdminCodec(self.publication_name),
                ),
            )
        self._links.log_subscriptions("construction")
        now = int(time.time())
        self._channels_reported = False
        self._last_report_second = int(now - (now % self.settings.seconds_per_report))
        self._last_snap_s = int(now - (now % self.settings.seconds_per_snapshot))
        self.pending_dispatch: Optional[AnalogDispatch] = None

        home_alone_normal = self.layout.node(H0N.home_alone_normal)
        self.set_command_tree(home_alone_normal)
        if actor_nodes is not None:
            for actor_node in actor_nodes:
                self.add_communicator(
                    ActorInterface.load(
                        actor_node.Name,
                        str(actor_node.actor_class),
                        self,
                        self.DEFAULT_ACTORS_MODULE,
                    )
                )
        self.top_state: TopState = TopState.Auto
        self.top_machine = Machine(
            model=self,
            states=Scada.top_states,
            transitions=Scada.top_transitions,
            initial=TopState.Auto,
            send_event=False,
            model_attribute="top_state",
        )
        self.auto_state: MainAutoState = MainAutoState.HomeAlone
        self.auto_machine = Machine(
            model=self,
            states=Scada.main_auto_states,
            transitions=Scada.main_auto_transitions,
            initial=MainAutoState.HomeAlone,
            send_event=False,
            model_attribute="auto_state",
        )
        self.timezone =  pytz.timezone(self.settings.timezone_str)
        self.contract_handler: ContractHandler = ContractHandler(
            settings=self.settings,
            layout=self.layout,
            node=self.node,
            logger=self.logger.add_category_logger(
                ContractHandler.LOGGER_NAME,
                level=settings.contract_rep_logging_level,
            )
        )
        self.initialize_hierarchical_state_data()
        self.state_machine_subscriptions: List[StateMachineSubscription] = [ 
             StateMachineSubscription(
                subscriber_name=self.sieg_loop.name,
                publisher_name=self.hp_boss.name
            )
        ]

        self.channel_subscriptions: Dict[str, ChannelSubscription] = {}

        # Initialize actuator tracking
        self.ready_actuators = set()
        self.all_actuators_ready = False

        # Define which actuators must report ready
        self.required_actuators = {
            self.relay_multiplexer, 
            self.zero_ten_out_multiplexer,
        }

        # Define which actors depend on actuator readiness
        self.actuator_dependents = {
            self.home_alone,
            self.sieg_loop,
            self.hp_boss,
        }

    def _start_derived_tasks(self):
        self._tasks.append(
            asyncio.create_task(self.report_sending_task(), name="report_sender")
        )
        self._tasks.append(
            asyncio.create_task(self.snap_sending_task(), name="snap_sender")
        )
        self._tasks.append(
            asyncio.create_task(self.state_tracker(), name="scada top_state_tracker")
        )

    #######################################
    # Messages
    #######################################

    def process_scada_message(self, from_node: ShNode, payload: Any) -> None:
        """Process NamedTypes sent to primary scada"""
        # Todo: turn msg into GwBase
        match payload:
            case ActuatorsReady():
                try:
                    self.process_actuators_ready(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_actuators_ready: \n {e}")
            case AdminDispatch():
                try:
                    self.process_admin_dispatch(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_admin_dispatch: \n {e}")
            case AdminKeepAlive():
                try:
                    self.process_admin_keep_alive(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_admin_keep_alive: \n {e}")
            case AdminReleaseControl():
                try:
                    self.process_admin_release_control(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with admin_release_control: \n {e}")
            case AllyGivesUp():
                try:
                    self.process_ally_gives_up(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_ally_gives_up: \n {e}")
            case AnalogDispatch():
                try:
                    self.process_analog_dispatch(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with proces_analog_dispatch: \n {e}")
            case ChannelFlatlined():
                try:
                    self.data.flush_channel_from_latest(payload.Channel.Name)
                except Exception as e:
                    self.log(f"Trouble with ChannelFlatlined: \n {e}")
            case ChannelReadings():
                try:
                    self.process_channel_readings(from_node, payload)
                except Exception as e:
                    self.logger.error(f"problem with process_channel_readings: \n {e}")
            case FsmFullReport():
                try:
                    self.process_fsm_full_report(from_node, payload)
                except Exception as e:
                    self.logger.error(f"problem with process_fsm_full_report: \n {e}")
            case Glitch():
                new_glitch = Glitch(
                    FromGNodeAlias=payload.FromGNodeAlias,
                    Node=payload.Node,
                    Type=payload.Type,
                    Summary=payload.Summary + " ...Went to Scada! Should go to Atn!",
                    Details=payload.Details,
                    CreatedMs=payload.CreatedMs
                )
                self._send_to(self.atn, new_glitch)
            case MachineStates():
                try:
                    self.process_machine_states(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_machine_states: \n {e}")
            case PowerWatts():
                try:
                    self.process_power_watts(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_power_watts: \n {e}")
            case ResetHpKeepValue():
                try:
                    self.process_reset_hp_keep_value(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_reset_hp_keep_value: \n {e}")
            case ScadaParams():
                try:
                    self.process_scada_params(from_node, payload)
                    self._send_to(self.synth_generator, payload)
                except Exception as e:
                    self.log(f"Trouble with process_scada_params: \n {e}")
            case SendLayout():
                try:
                    self._send_to(from_node, self.layout_lite)
                except Exception as e:
                    self.log(f"Trouble with SendLayout: {e}")
            case SendSnap():
                try:
                    self._send_to(from_node, self._data.make_snapshot())
                except Exception as e:
                    self.log(f"Trouble with SendSnap: {e}")
            case SetLwtControlParams():
                try:
                    self.process_set_lwt_control_params(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_set_lwt_control_params: {e}")
            case SetTargetLwt():
                try:
                    self.process_set_target_lwt(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_set_target_lwt: {e}")
            case SiegLoopEndpointValveAdjustment():
                try:
                    self.process_sieg_loop_endpoint_valve_adjustment(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_sieg_loop_endpoint_valve_adjustment: \n {e}")
            case SiegTargetTooLow():
                # send up to atn so we have a record
                self._send_to(self.atn, payload)
            case SingleMachineState():
                try:
                    self.process_single_machine_state(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_single_machine_state_: \n {e}")
            case SingleReading():
                try:
                    self.process_single_reading(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_single_reading: \n {e}")
            case SlowContractHeartbeat():
                try:
                    self.process_slow_contract_heartbeat(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_slow_contract_heartbeat: \n {e}")
            case SuitUp():
                try:
                    self.process_suit_up(from_node, payload)
                except Exception as e:
                    self.logger.error(f"Trouble with process_suit_up: \n {e}")
            case SyncedReadings():
                try:
                    self.process_synced_readings(from_node, payload)
                except Exception as e:
                    self.log(f"Trouble with process_synced_reading: \n {e}")
            case _:
                raise ValueError(f"Scada does not expect to receive[{type(payload)}!]")

    #####################################################################
    # Process Messages
    #####################################################################

    def process_actuators_ready(
            self, from_node: ShNode, payload: ActuatorsReady
    ) -> None:
        """Tracks which actuators are ready and notifies dependent actors when all are ready"""
        self.ready_actuators.add(from_node)
        self.log(f"Actuator {from_node.name} is ready. {len(self.ready_actuators)}/{len(self.required_actuators)}")

        # Check if all required actuators are ready
        if self.required_actuators.issubset(self.ready_actuators):
            self.all_actuators_ready = True
            self.log("All actuators are ready!")
            # Notify dependent actors that need to know when actuators are ready
            for dependent in self.actuator_dependents:
                self._send_to(dependent, ActuatorsReady())

    def process_admin_dispatch(
        self, from_node: ShNode, payload: AdminDispatch
    ) -> None:
        if from_node != self.admin:
            self.log(f"Ignoring AdminDispatch from {from_node.name}. Expected admin!")

        if not self.top_state == TopState.Admin:
            self.admin_wakes_up()
            self.log("Admin Wakes Up")
        self._renew_admin_timeout(timeout_seconds=payload.TimeoutSeconds)
        event = payload.DispatchTrigger
        self.log(f"AdminDispatch event is {event.EventName}")

        to_name = event.ToHandle.split(".")[-1]
        # TODO: change this to work if relays etc are NOT on primary scada
        if communicator := self.get_communicator(to_name):
            communicator.process_message(
                Message(
                    header=Header(
                        Src=H0N.admin,
                        Dst=communicator.name,
                        MessageType=event.TypeName,
                    ),
                    Payload=event,
                )
            )

    def process_admin_release_control(
        self, from_node: ShNode, payload: AdminReleaseControl
    ) -> None:
        if from_node != self.admin:
            self.log(
                f"Ignoring AdminReleaseControl from {from_node.Name} - expected admin"
            )
            return
        if self.top_state != TopState.Admin:
            self.log("Ignoring AdminReleaseControl, TopState not Admin")
            return
        # AdminReleasesControl:  Admin => Auto
        self.AdminReleasesControl()
        self.log(f"Admin releases control: {self.top_state}")
        # cancel the timeout
        if self._admin_timeout_task is not None:
            if not self._admin_timeout_task.cancelled():
                self._admin_timeout_task.cancel()
            self._admin_timeout_task = None
            # wake up auto state, which has been dormant. This will set
        # the actuator forest to HomeAlone
        self.auto_wakes_up()

    def process_admin_keep_alive(
        self, from_node: ShNode, payload: AdminKeepAlive
    ) -> None:
        if from_node != self.admin:
            self.log(f"Ignoring AdminKeepAlive from {from_node.name}. Expected admin!")

        self._renew_admin_timeout(timeout_seconds=payload.AdminTimeoutSeconds)
        self.log(f"Admin timeout renewed: {payload.AdminTimeoutSeconds} seconds")
        if not self.top_state == TopState.Admin:
            self.admin_wakes_up()
            self.log("Admin Wakes Up")

    def process_ally_gives_up(self, from_node: ShNode, payload: AllyGivesUp) -> None:
        # AutoState transition: AllyGivesUp: Atn -> HomeAlone
        self.auto_trigger(MainAutoEvent.AllyGivesUp)
        self.log(f"Atomic Ally giving up: {payload.Reason}")
        self.log("Sending termination hb to Scada. State: Atn -> HomeAlone")
        hb = self.contract_handler.scada_terminates_contract_hb(cause=f"Ally Gives up: {payload.Reason}")
        self._send_to(self.atn, hb)
        # Cancel any existing warning task
        if hasattr(self, 'contract_task'):
            self.contract_task.cancel()

    def process_analog_dispatch(
        self, from_node: ShNode, payload: AnalogDispatch
    ) -> None:
        if payload.FromGNodeAlias != self._layout.atn_g_node_alias:
            self.logger.error("IGNORING DISPATCH - NOT FROM MY ATN")
            return
        # HUGE HACK - 
        to_node = self.layout.node(payload.AboutName)
        boss_handle = '.'.join(to_node.handle.split('.')[:-1])
        self.log(f"About name is {payload.AboutName}")
        self._send_to(to_node, AnalogDispatch(FromGNodeAlias=payload.FromGNodeAlias,
                                              FromHandle=boss_handle,
                                              ToHandle=to_node.handle,
                                              AboutName=to_node.name,
                                              Value=payload.Value,
                                              TriggerId=payload.TriggerId,
                                              UnixTimeMs=payload.UnixTimeMs))
        # to_node = self.layout.node_by_handle(payload.ToHandle)
        # if to_node:gi
        #     self.log(f"Sending to {to_node.Name}")
        #     self._send_to(to_node.Name, payload)

    def process_channel_readings(
        self, from_node: ShNode, payload: ChannelReadings
    ) -> None:
        if payload.ChannelName not in self._layout.data_channels:
            raise ValueError(
                f"Name {payload.ChannelName} in ChannelReadings not a recognized Data Channel!"
            )
        ch = self._layout.data_channels[payload.ChannelName]
        if from_node != ch.captured_by_node:
            raise ValueError(
                f"{payload.ChannelName} shoudl be read by {ch.captured_by_node}, not {from_node}!"
            )
        self._data.recent_channel_values[ch.Name] += payload.ValueList

        self._data.recent_channel_unix_ms[ch.Name] += payload.ScadaReadTimeUnixMsList
        if len(payload.ValueList) > 0:
            self._data.latest_channel_values[ch.Name] = payload.ValueList[-1]
            self._data.latest_channel_unix_ms[
                ch.Name
            ] = payload.ScadaReadTimeUnixMsList[-1]

    def process_fsm_full_report(
        self, from_node: ShNode, payload: FsmFullReport
    ) -> None:
        self._data.recent_fsm_reports[payload.TriggerId] = payload

    def process_reset_hp_keep_value(
            self, from_node: ShNode, payload: ResetHpKeepValue
    ) -> None:
        to_node = self.sieg_loop
        if to_node is None:
            self.log(f"Ignoring reset.hp.keep.value to {payload.ToHandle} -> not a known node")
            return
        boss = self.layout.boss_node(to_node)
        if boss is None:
            self.log(f"That's funny! no boss for {payload.ToHandle}")
            return
        if to_node.Handle is None:
            return
        if boss.Handle is None:
            return
        new_payload = ResetHpKeepValue(FromHandle=boss.Handle, ToHandle=to_node.Handle,
                                       FromValue=payload.FromValue, ToValue=payload.ToValue)
        self.log(f"Got ResetHpKeepValue. Sending {new_payload} to {to_node.Name} from {boss.name}")
        self._send_to(to_node, new_payload, boss)

    def process_machine_states(
        self, from_node: ShNode, payload: MachineStates
    ) -> None:
        node_name = payload.MachineHandle.split('.')[-1]
        if node_name in self._data.recent_machine_states:
            prev: MachineStates = self._data.recent_machine_states[
                node_name
            ]
            if payload.StateEnum != prev.StateEnum:
                raise Exception(
                    f"{payload.MachineHandle} has conflicting state machines!"
                    f"{payload.StateEnum} and {prev.StateEnum}"
                )

            self._data.recent_machine_states[node_name] = MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                UnixMsList=prev.UnixMsList + payload.UnixMsList,
                StateList=prev.StateList + payload.StateList,
            )
        else:
            self._data.recent_machine_states[node_name] = payload
       
        self._data.latest_machine_state[node_name] = SingleMachineState(
            MachineHandle=payload.MachineHandle,
            StateEnum=payload.StateEnum,
            State=payload.StateList[-1],
            UnixMs=payload.UnixMsList[-1]
        )

    def process_power_watts(self, from_node: ShNode, payload: PowerWatts):
        """Highest priority of scada is to pass this on to Atn

        also call contract_handler.update_energy_usage
        """
        self._send_to(self.atn, payload)
        # Update internal data store
        # Update contract energy tracking if contract is active
        if self.contract_handler.latest_scada_hb:
            self.contract_handler.update_energy_usage(payload.Watts)

    def process_scada_params(
        self, from_node: ShNode, payload: ScadaParams, testing: bool = False
    ) -> None:
        if from_node != self.atn:
            self.log(f"ScadaParams from {from_node.Name}; expect Atn!")
            return
        if payload.FromGNodeAlias != self.hardware_layout.atn_g_node_alias:
            self.log(
                f"ScadaParams from {payload.FromGNodeAlias}; expect {self.hardware_layout.atn_g_node_alias}!"
            )
            return
        new = payload.NewParams
        if new:
            old = self.data.ha1_params
            self.data.ha1_params = new
            if new.AlphaTimes10 != old.AlphaTimes10:
                self.update_env_variable("SCADA_ALPHA", new.AlphaTimes10 / 10)
            if new.BetaTimes100 != old.BetaTimes100:
                self.update_env_variable("SCADA_BETA", new.BetaTimes100 / 100)
            if new.GammaEx6 != old.GammaEx6:
                self.update_env_variable("SCADA_GAMMA", new.GammaEx6 / 1e6)
            if new.IntermediatePowerKw != old.IntermediatePowerKw:
                self.update_env_variable(
                    "SCADA_INTERMEDIATE_POWER", new.IntermediatePowerKw
                )
            if new.IntermediateRswtF != old.IntermediateRswtF:
                self.update_env_variable(
                    "SCADA_INTERMEDIATE_RSWT", new.IntermediateRswtF
                )
            if new.DdPowerKw != old.DdPowerKw:
                self.update_env_variable(
                    "SCADA_DD_POWER", new.DdPowerKw, testing=testing
                )
            if new.DdRswtF != old.DdRswtF:
                self.update_env_variable("SCADA_DD_RSWT", new.DdRswtF)
            if new.DdDeltaTF != old.DdDeltaTF:
                self.update_env_variable("SCADA_DD_DELTA_T", new.DdDeltaTF)
            if new.LoadOverestimationPercent != old.LoadOverestimationPercent:
                self.update_env_variable(
                    "SCADA_LOAD_OVERESTIMATION_PERCENT", new.LoadOverestimationPercent
                )

            response = ScadaParams(
                FromGNodeAlias=self.hardware_layout.scada_g_node_alias,
                FromName=self.name,
                ToName=payload.FromName,
                UnixTimeMs=int(time.time() * 1000),
                MessageId=payload.MessageId,
                NewParams=self.data.ha1_params,
                OldParams=old,
            )
            self.logger.error(f"Sending back {response}")
            self._send_to(self.atn, response)

    def process_set_lwt_control_params(
            self, from_node: ShNode, payload: SetLwtControlParams
    ) -> None:
        to_node = self.sieg_loop
        if to_node is None:
            self.log(f"Ignoring set.lwt.control.params to {payload.ToHandle} -> not a known node")
            return
        boss = self.layout.boss_node(to_node)
        if boss is None:
            self.log(f"That's funny! no boss for {payload.ToHandle}")
            return
        if to_node.Handle is None:
            return
        if boss.Handle is None:
            return
        payload.ToHandle = to_node.Handle
        payload.FromHandle = boss.Handle
        self._send_to(to_node, payload, boss)

    def process_set_target_lwt(
            self, from_node: ShNode, payload: SetTargetLwt
    ) -> None:
        to_node = self.sieg_loop
        if to_node is None:
            self.log(f"Ignoring set.target.lwt to {payload.ToHandle} -> not a known node")
            return
        boss = self.layout.boss_node(to_node)
        if boss is None:
            self.log(f"That's funny! no boss for {payload.ToHandle}")
            return
        if to_node.Handle is None:
            return
        if boss.Handle is None:
            return
        payload.ToHandle = to_node.Handle
        payload.FromHandle = boss.Handle
        self._send_to(to_node, payload, boss)

    def process_sieg_loop_endpoint_valve_adjustment(
        self, from_node: ShNode, payload: SiegLoopEndpointValveAdjustment
    ) -> None:
        to_node = self.sieg_loop
        if to_node is None:
            self.log(f"Ignoring reset.hp.keep.value to {payload.ToHandle} -> not a known node")
            return
        boss = self.layout.boss_node(to_node)
        if boss is None:
            self.log(f"That's funny! no boss for {payload.ToHandle}")
            return
        if to_node.Handle is None:
            return
        if boss.Handle is None:
            return
        new_payload = SiegLoopEndpointValveAdjustment(FromHandle=boss.Handle, ToHandle=to_node.Handle,
                                        HpKeepPercent=payload.HpKeepPercent, Seconds=payload.Seconds)
        self.log(f"GotSiegLoopEndpointValveAdjustment. Sending to {to_node.Name}")
        self._send_to(to_node, new_payload, boss)

    def process_single_machine_state(
        self, from_node: ShNode, payload: SingleMachineState
    ) -> None:
        # TODO: compare MachineHandle last word with from_node.Name
        if payload.MachineHandle in self._data.recent_machine_states:
            prev: MachineStates = self._data.recent_machine_states[
                payload.MachineHandle
            ]
            if payload.StateEnum != prev.StateEnum:
                raise Exception(
                    f"{payload.MachineHandle} has conflicting state machines!"
                    f"{payload.StateEnum} and {prev.StateEnum}"
                )
            self._data.recent_machine_states[payload.MachineHandle] = MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                UnixMsList=prev.UnixMsList + [payload.UnixMs],
                StateList=prev.StateList + [payload.State],
            )
        else:
            self._data.recent_machine_states[payload.MachineHandle] = MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                StateList=[payload.State],
                UnixMsList=[payload.UnixMs],
            )
        node_name = payload.MachineHandle.split('.')[-1]
        self._data.latest_machine_state[node_name] = payload
        self.handle_state_change_subscriptions(from_node, payload)

    def handle_state_change_subscriptions(self, from_node: ShNode, sms: SingleMachineState) -> None:
        # Find all subscriptions for this publisher (from_node)
        for subscription in self.state_machine_subscriptions:
            if subscription.publisher_name == from_node.Name:
                # Get the subscriber node
                subscriber_node = self._layout.node(subscription.subscriber_name)
                if subscriber_node is not None:
                    self.log(f"Sending {sms.MachineHandle} state to {subscriber_node.name}")
                    self._send_to(
                        to_node=subscriber_node,
                        payload=sms,
                        from_node=from_node
                    )
                else:
                    self.log(f"Subscriber {subscription.subscriber_name} not found for state change from {from_node.Name}")


    def process_single_reading(
        self, from_node: ShNode, payload: SingleReading
    ) -> None:
        if payload.ChannelName in self._layout.data_channels:
            ch = self._layout.data_channels[payload.ChannelName]
        elif payload.ChannelName in self._layout.synth_channels:
            ch = self._layout.synth_channels[payload.ChannelName]
        else:
            raise Exception(f"Missing channel name {payload.ChannelName}!")
        self._data.recent_channel_values[ch.Name].append(payload.Value)
        self._data.recent_channel_unix_ms[ch.Name].append(payload.ScadaReadTimeUnixMs)
        self._data.latest_channel_values[ch.Name] = payload.Value
        self._data.latest_channel_unix_ms[ch.Name] = payload.ScadaReadTimeUnixMs
        self._forward_single_reading(payload)

    def process_suit_up(self, from_node: ShNode, payload: SuitUp) -> None:
        if from_node.Name != H0N.atomic_ally:
            self.log(
                f"Ignoring AllySuitsUp from {from_node.Name} - expect AtomicAlly (aa)"
            )
            return
        # TODO: think through state machine
        # tell the atomic transactive node that game is on
        self.process_new_contract()
        self._send_to(self.atn, self.contract_handler.latest_scada_hb)

    def process_synced_readings(self, from_node: ShNode, payload: SyncedReadings):
        self._logger.path(
            "++process_synced_readingsfrom: %s  channels: %d",
            from_node.Name,
            len(payload.ChannelNameList),
        )
        path_dbg = 0
        for idx, channel_name in enumerate(payload.ChannelNameList):
            path_dbg |= 0x00000001
            if channel_name not in self._layout.data_channels:
                raise ValueError(
                    f"Name {channel_name} in payload.SyncedReadings not a recognized Data Channel!"
                )
            ch = self._layout.data_channels[channel_name]
            self._data.recent_channel_values[ch.Name].append(payload.ValueList[idx])
            self._data.recent_channel_unix_ms[ch.Name].append(
                payload.ScadaReadTimeUnixMs
            )
            self._data.latest_channel_values[ch.Name] = payload.ValueList[idx]
            self._data.latest_channel_unix_ms[ch.Name] = payload.ScadaReadTimeUnixMs

    #####################################################################
    # State Machine related
    #####################################################################

    # Top States: Admin, Auto
    # Top Events: AdminWakesUp, AdminTimesOut, AdminReleasesControl

    def initialize_hierarchical_state_data(self) -> None:
        """ Scada TopState: Auto, Scada Auto: HomeAlone
          HomeAlone: Normal, AtomicAlly: Dormant

        """
        now_ms = int(time.time() * 1000)
        self.data.latest_machine_state[self.name] = SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=TopState.enum_name(),
                State=TopState.Auto,
                UnixMs=now_ms,
            )
        
        # AtomicAlly is Dormant
        self.data.latest_machine_state[self.atomic_ally.name] = SingleMachineState(
                MachineHandle=self.atomic_ally.handle,
                StateEnum=AtomicAllyState.enum_name(),
                State=AtomicAllyState.Dormant,
                UnixMs=now_ms,
            )
        
        # HomeAloneTopState is Normal
        self.data.latest_machine_state[self.home_alone.name] = SingleMachineState(
                MachineHandle=self.node.handle,
                StateEnum=HomeAloneTopState.enum_name(),
                State=HomeAloneTopState.Normal,
                UnixMs=now_ms,
            )

        # TODO: Add auto state and pico cylcer


    def admin_wakes_up(self) -> None:
        if self.top_state == TopState.Admin:
            self.log("Ignoring AdminWakesUp, TopState already Admin")
            return
        # Trigger the AdminWakesUp event for top state:  Auto => Admin
        self.AdminWakesUp()
        self.log(f"Message from Admin! top_state {self.top_state}")
        if self.auto_state == MainAutoState.Dormant:
            self.log("AdminWakesUp called when auto state was dormant!!")
            return
        # This will set auto_state and update the actuator forest to Admin
        self.auto_trigger(MainAutoEvent.AutoGoesDormant)

    def admin_times_out(self) -> None:
        if self.top_state == TopState.Auto:
            self.log("Ignoring AdminTimesOut, TopState already Auto")
            return

        # AdminTimesOut: Admin => Auto
        self.AdminTimesOut()
        self.log(f"Admin timed out! {self.top_state}")
        # cancel the timeout
        if self._admin_timeout_task is not None:
            if not self._admin_timeout_task.cancelled():
                self._admin_timeout_task.cancel()
            self._admin_timeout_task = None

        # wake up auto state, which has been dormant. This will set
        # the actuator forest to HomeAlone
        self.auto_wakes_up()

    # AUTO STATE MACHINE

    def auto_trigger(self, trigger: MainAutoEvent) -> None:
        """ Pulls trigger, updates command tree and sends appropriate messages
        """
        if trigger == MainAutoEvent.DispatchContractLive:
            if self.auto_state != MainAutoState.HomeAlone:
                self.log(f"Ignoring DispatchContractLive tigger in auto_state {self.auto_state}")
                return
            if not self.contract_handler.latest_scada_hb:
                self.log("Ignoring DispatchContractLive trigger! No latest_scada_hb")
                return
            contract = self.contract_handler.latest_scada_hb.Contract
            self.DispatchContractLive()
            self.log("DispatchContractLive: HomeAlone -> Atn")
            self.set_command_tree(self.atomic_ally)
            # Wake up atn, tell home alone to go dormant
            self._send_to(self.atomic_ally, contract)
            self._send_to(self.home_alone, GoDormant(ToName=self.home_alone.name)
            )
        elif trigger == MainAutoEvent.ContractGracePeriodEnds:
            if self.auto_state != MainAutoState.Atn:
                self.log(f"Ignoring ContractGracePeriodEnds trigger in auto_state {self.auto_state}")
                return
            self.ContractGracePeriodEnds()
            self.log("ContractGracePeriodEnds: Atn -> HomeAlone")
            self.set_command_tree(self.home_alone)
            self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
            self._send_to(self.atomic_ally, GoDormant(ToName=H0N.atomic_ally))
        elif trigger == MainAutoEvent.AtnReleasesControl:
            if self.auto_state != MainAutoState.Atn:
                self.log(f"Ignoring AtnReleasesControl trigger in auto_state {self.auto_state}")
                return
            self.AtnReleasesControl()
            self.log("AtnReleasesControls: Atn -> HomeAlone")
            self.set_command_tree(self.home_alone)
            self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
            self._send_to(self.atomic_ally, GoDormant(ToName=H0N.atomic_ally))
        elif trigger == MainAutoEvent.AllyGivesUp:
            if self.auto_state != MainAutoState.Atn:
                self.log(f"Ignoring AllyGivesUp trigger in auto_state {self.auto_state}")
                return
            self.AllyGivesUp()
            self.log("AllyGivesUp: Atn -> HomeAlone")
            self.set_command_tree(self.home_alone)
            self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
            self._send_to(self.atomic_ally, GoDormant(ToName=H0N.atomic_ally))
        elif trigger == MainAutoEvent.AutoGoesDormant:
            if self.auto_state == MainAutoState.Dormant:
                self.log(f"Ignoring AutoWakesUp trigger in auto_state {self.auto_state}")
                return
            prev_state = self.auto_state
            self.AutoGoesDormant()
            self.log(f"AutoGoesDormant: {prev_state} -> {self.auto_state}")
            # ADMIN CONTROL FOREST: a single tree, controlling all actuators
            self.set_command_tree(self.admin)

            # Let the active nodes know they've lost control of their actuators
            for direct_report in [self.atomic_ally,self.home_alone,self.layout.pico_cycler]:
                self._send_to(
                    direct_report, GoDormant(ToName=direct_report.Name)
                )
        elif trigger == MainAutoEvent.AutoWakesUp:
            if self.auto_state != MainAutoState.Dormant:
                self.log(f"Ignoring AutoWakesUp trigger in auto_state {self.auto_state}")
                return
            self.AutoWakesUp()
            self.log("AutoWakesUp: Dormant -> HomeAlone")
            self.set_command_tree(self.home_alone)
            self._send_to(self.home_alone, WakeUp(ToName=H0N.home_alone))
            self._send_to(self.layout.pico_cycler, WakeUp(ToName=H0N.pico_cycler))
            
    def auto_wakes_up(self) -> None:
        """
        Goes to HomeAlone. Then if in grace period, triggers DispatchContractLive
        """
        if self.auto_state != MainAutoState.Dormant:
            self.log(f"STRANGE!! auto state is already{self.auto_state}")
            return
        # Trigger AutoWakesUp for auto state: Dormant -> HomeAlone
        self.auto_trigger(MainAutoEvent.AutoWakesUp)
        if self.contract_handler.latest_scada_hb:
            self.auto_trigger(MainAutoEvent.DispatchContractLive)

    def process_slow_contract_heartbeat(self, from_node: ShNode, atn_hb: SlowContractHeartbeat) -> None:

        self.log(f"{self.contract_handler.formatted_contract(atn_hb)}")
        return_hb = None
        if atn_hb.Status == ContractStatus.Created:
            if self.top_state == TopState.Admin:
                self.log("Ignoring new contract, in Admin")
                return
            if self.contract_handler.latest_scada_hb is None: # contract already wrapped up
                return_hb = self.contract_handler.start_new_contract_hb(atn_hb) #sets up matching latest_scada_hb
                if self.auto_state == MainAutoState.HomeAlone:
                    self.dispatch_contract_live() # sets up the trees, changes state, let's aa and h know
            elif self.contract_handler.active_contract_has_expired(): # wrap up existing
                self._send_to(self.atn,
                    self.contract_handler.scada_contract_completion_hb("Wrapping up existing contract")
                )
                self.contract_handler.start_new_contract_hb(atn_hb)
                self._send_to(self.atomic_ally, self.contract_handler.latest_scada_hb.Contract
                )
                # will send hb in process_suit_up, after atomic ally acknowledges
        elif atn_hb.Status == ContractStatus.TerminatedByAtn:
            raise Exception("Ack! Haven't thought through termination by atn ...")
        else:
            if self.contract_handler.latest_scada_hb is None:
                self.log(f"got continuation hb when Scada has no contract! ignoring:  {atn_hb.Contract}")
                return
            if self.contract_handler.latest_scada_hb.Contract.ContractId != atn_hb.Contract.ContractId:
                self.log(f"Got inbound hb with contract mismatch! \n inbound: {atn_hb}"
                f"existing: {self.contract_handler.latest_scada_hb}")
                return
            return_hb = self.contract_handler.update_existing_contract_hb(atn_hb)

        if return_hb:
            self._send_to(self.atn, return_hb) # on completion, will send back a completion
            # hb with final energy_used_wh

    def process_new_contract(self) -> None:
        """Called after contract is confirmed (SuitUp received)"""
        # Cancel any existing timers
        if hasattr(self, 'contract_task'):
            self.contract_task.cancel()

        if self.contract_handler.latest_scada_hb is None:
            return
        contract = self.contract_handler.latest_scada_hb.Contract
        
        # Schedule new warning
        self.contract_task = asyncio.create_task(
            self.handle_contract_timing(),
            name=f"contract_task_{contract.ContractId}"
        )

    def in_grace_period(self) -> bool:
        """Scada is NOT dormant, and a contract is active or was active within 5 minutes
        Effect: if contract_handler.active_contract_has_expired, send a final
        completion heartbeat, None -> latest_scada_hb -> prev
        """
        if self.contract_handler.active_contract_has_expired():
                self._send_to(self.atn,
                        self.contract_handler.scada_contract_completion_hb("Active contract has expired"))
        if self.contract_handler.latest_scada_hb: # will not be expired
            return True
        elif not self.contract_handler.prev:
            return False
        elif time.time() > self.contract_handler.prev.grace_period_end_s():
            return False
        else:
            return True

    async def handle_contract_timing(self):
        """Handles warning messages and state transition out of atn if needed.

        Atn is meant to be the actor that terminates each contract but Scada also
        provided backup for that here.
        """
        hb = self.contract_handler.latest_scada_hb
        if hb is None:
            return

        actual_end_s = hb.Contract.contract_end_s()
        if hb.Status == ContractStatus.TerminatedByScada:
            actual_end_s = hb.MessageCreatedMs / 1000
        delay_s = (actual_end_s +
                        self.contract_handler.WARNING_MINUTES_AFTER_END * 60 - time.time())
        await asyncio.sleep(delay_s)

        grace_end_s = int(actual_end_s+ self.contract_handler.GRACE_PERIOD_MINUTES* 60)
        # Case 1: latest_scada_hb is None - old contract was properly expired
        # Still send warning since we haven't received a new contract
        if not self.contract_handler.latest_scada_hb:
            self._send_to(self.atn, NoNewContractWarning(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ContractId=hb.Contract.ContractId,
                GraceEndTimeS=grace_end_s
            ))
            return
         # Case 2: We have a different contract after the wait - this is the normal
         # case where the old contract expired and atn sent a new one
        if self.contract_handler.latest_scada_hb.Contract.ContractId != hb.Contract.ContractId:
            return
        # Case 3: Same contract still active - needs to be completed
        self.log(f"Contract {hb.Contract.ContractId} end time reached - sending completion")

        # Send completion heartbeat and set contract_handler.latest_scada_hb to None
        completion_hb = self.contract_handler.scada_contract_completion_hb("Noticed active contract complete")
        self._send_to(self.atn, completion_hb)

        # Set backup timer for grace period
        grace_remaining = (self.contract_handler.GRACE_PERIOD_MINUTES -
                        self.contract_handler.WARNING_MINUTES_AFTER_END) * 60
        await asyncio.sleep(grace_remaining)

        # If still same contract after grace period, force transition to home alone
        if not self.in_grace_period():
            self.log(f"Grace period expired for contract {hb.Contract.ContractId} - transitioning to home alone")
            self.auto_trigger(MainAutoEvent.ContractGracePeriodEnds)

    def dispatch_contract_live(self) -> None:
        """ DispatchContractLive: HomeAlone -> Atn
        Includes a new (or existing) latest_scada_hb
          - Triggers state change for AutoState
          - Sets Atn Command Tree
          - Tells HomeAlone and AtomicAlly
        """
        if self.top_state == TopState.Admin:
            self.log("That's strange - expect TopState auto here.")
            return

        if self.contract_handler.latest_scada_hb is None:
            raise Exception("Should be called AFTER setting latest_scada_hb!")
        self.log("New Dispatch Contract!")

        if self.auto_state == MainAutoState.HomeAlone:
            self.auto_trigger(MainAutoEvent.DispatchContractLive)
        # Regardless of auto state
        if self.contract_handler.latest_scada_hb is None:
            self.log("That's strange! There should be a latest_scada_hb!")
            return
        self._send_to(self.atomic_ally, self.contract_handler.latest_scada_hb.Contract
        )

    def _derived_recv_activated(
        self, transition: Transition
    ) -> Result[bool, BaseException]:
        """Overwrites base method. Triggered when link state is activated"""
        if transition.link_name == self.upstream_client:
            self._send_to(self.atn, self.layout_lite)
        return Ok()

    ###########################################################
    # Command Trees - the handles of the Spaceheat Nodes form a tree
    # where the line of direct report is required for following a command
    ##########################################################

    def set_command_tree(self, boss: ShNode) -> None:
        """ Command Tree
        If FlowManifoldVariant is House0Sieg:
        ```
        boss                                                 pico-flow
        ├───────────────────────────────────────── hp-boss      └── relay1 (VDC)
        ├──────────────────────────────sieg-loop     └── relay6 (hp_scada_ops_relay)                                          
        ├── relay2 (tstat_common)        ├─ relay14 (hp_loop_on_off)
        └── all other relays and 0-10s   └─ relay15 (hp_loop_keep_send)
        
        
        ```
        If FlowManifoldVariant is House0, all actuators other than relay1 report 
        directly to boss.

        If boss is admin, then all relays report directly to admin
        """

        if self.layout.flow_manifold_variant == FlowManifoldVariant.House0:
            for node in self.layout.actuators:
                if node.Name == H0N.vdc_relay and boss != self.admin:
                    node.Handle = f"{H0N.auto}.{H0N.pico_cycler}.{node.Name}"
                else:
                    node.Handle = (f"{boss.handle}.{node.Name}")
        elif self.layout.flow_manifold_variant == FlowManifoldVariant.House0Sieg:
            hp_boss = self.layout.node(H0N.hp_boss)
            hp_boss.Handle = f"{boss.handle}.{hp_boss.Name}"
            
            sieg_loop = self.layout.node(H0N.sieg_loop)
            sieg_loop.Handle = f"{boss.handle}.{H0N.sieg_loop}"

            for node in self.layout.actuators:
                if node.Name == H0N.vdc_relay and boss != self.admin:
                    node.Handle = f"{H0N.auto}.{H0N.pico_cycler}.{node.Name}"
                elif node.Name == H0N.hp_scada_ops_relay:
                    node.Handle = f"{boss.handle}.{hp_boss.Name}.{node.Name}"
                elif node.Name in [H0N.hp_loop_keep_send, H0N.hp_loop_on_off]:
                    node.Handle = f"{boss.handle}.{H0N.sieg_loop}.{node.Name}"
                else:
                    node.Handle = (f"{boss.handle}.{node.Name}")
        else:
            raise Exception(f"Unknown FlowManifoldVariant {self.layout.flow_manifold_variant}")

        self._send_to(
            self.atn,
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            ),
        )

    #######################################
    # Contract management
    #######################################

    def initialize_contracts(self) -> None:
        """Called during Scada startup to load any persisted contracts"""

        # loads state and contract from persistent store
        hb = self.contract_handler.initialize()

        # Re-establish ATN mode if contract is live
        if self.contract_handler.latest_scada_hb:
            self.dispatch_contract_live()

        if hb:
            self._send_to(self.atn, hb)
            self._send_to(self.atomic_ally, hb)
    
    def enforce_auto_state_consistency(self) -> None:
        """ Enforces that auto_state [Atn, HomeAlone, Dormant] is consistent
        with the top_state reported by `h` [Dormant v anything else] and `aa` [Dormant v anything else]
        """
        
        h: HomeAlone = self.get_communicator(H0N.home_alone)
        aa: AtomicAlly = self.get_communicator(H0N.atomic_ally)

        
        #aa_state = self.data.latest_machine_state[self.atomic_ally.name].State
        #h_state = self.data.latest_machine_state[self.home_alone.name].State
        aa_state = aa.state
        h_state = h.top_state

        if self.auto_state == MainAutoState.Dormant:
            if aa_state != AtomicAllyState.Dormant:
                self.log(f"Noticed auto_state Dormant but AtomicAlly in {aa_state}! Sending GoDormant")
                self._send_to(self.atomic_ally, GoDormant(ToName=self.atomic_ally.name))
            if h_state != HomeAloneTopState.Dormant:
                self.log(f"Noticed auto_state Dormant but HomeAlone in {h_state}! Sending GoDormant")
                self._send_to(self.home_alone, GoDormant(ToName=self.home_alone.name))
        elif self.auto_state == MainAutoState.Atn:
            if not self.in_grace_period():
                self.log("Noticed auto_state Atn but no longer in grace period!")
                self.auto_trigger(MainAutoEvent.ContractGracePeriodEnds)
                return 
            if aa_state == AtomicAllyState.Dormant:
                self.log("Noticed auto_state Atn but AtomicAlly Dormant!")
                if self.contract_handler.latest_scada_hb:
                    contract = self.contract_handler.latest_scada_hb.Contract
                    self._send_to(self.atomic_ally, contract)  # This is how the Atn wakes up
                else: # we might be in the grace period of an expired contract ... this check will 
                    self.log("No contract but in grace period. This will correct in 5 minutes")
            if h_state != HomeAloneTopState.Dormant:
               self.log(f"Noticed auto_state Atn but HomeAlone in {h_state}! Sending GoDormant")
               self._send_to(self.home_alone, GoDormant(ToName=self.home_alone.name))
        elif self.auto_state == MainAutoState.HomeAlone:
            if aa_state != AtomicAllyState.Dormant:
                self.log(f"Noticed auto_state HomeAlone but AtomicAlly in {aa_state}! Sending GoDormant")
                self._send_to(self.atomic_ally, GoDormant(ToName=self.atn.name))
            if h_state == HomeAloneTopState.Dormant:
               self.log("Noticed auto_state HomeAlone but home_alone Dormant! Sending WakeUp")
               self._send_to(self.home_alone, WakeUp(ToName=self.home_alone.name))

    async def state_tracker(self) -> None:
        loop_s = self.settings.seconds_per_report
        await asyncio.sleep(4)
        self.log("About to initialize contracts")
        self.initialize_contracts()
        while True:
            hiccup = 1.5
            sleep_s = max(hiccup, loop_s - (time.time() % loop_s) - 1.2)
            await asyncio.sleep(sleep_s)
            self.enforce_auto_state_consistency() # e.g. if self.auto_state is Atn, then AtomicAlly is NOT Dormant
            # report the state
            if sleep_s != hiccup:
                self._send_to(
                    self.node,
                    MachineStates(
                        MachineHandle=self.node.handle,
                        StateEnum=TopState.enum_name(),
                        StateList=[self.top_state],
                        UnixMsList=[int(time.time() * 1000)],
                    ),
                )

                self._send_to(
                    self.node,
                    MachineStates(
                        MachineHandle=self.layout.auto_node.handle,
                        StateEnum=MainAutoState.enum_name(),
                        StateList=[self.auto_state],
                        UnixMsList=[int(time.time() * 1000)],
                    ),
                )
                self.logger.warning(f"Top state: {self.top_state}")
                self.logger.warning(f"Auto state: {self.auto_state}")


    #############################################
    # Core synchronous reporting tasks: reports (all timestamped sensing data)
    # and snapshots (latest snapshots)
    ##############################################

    def next_report_second(self) -> int:
        last_report_second_nominal = int(
            self._last_report_second
            - (self._last_report_second % self.settings.seconds_per_report)
        )
        return last_report_second_nominal + self.settings.seconds_per_report

    def next_snap_second(self) -> int:
        last_snap_nominal = int(
            self._last_snap_s - (self._last_snap_s % self.settings.seconds_per_snapshot)
        )
        return last_snap_nominal + self.settings.seconds_per_snapshot

    def seconds_til_next_report(self) -> float:
        return self.next_report_second() - time.time()

    def seconds_til_next_snap(self) -> float:
        return self.next_snap_second() - time.time()

    def time_to_send_report(self) -> bool:
        return time.time() > self.next_report_second()

    def time_to_send_snap(self) -> bool:
        return time.time() > self.next_snap_second()

    def send_report(self):
        report = self._data.make_report(self._last_report_second)
        self._data.reports_to_store[report.Id] = report
        self.generate_event(ReportEvent(Report=report))  # noqa
        self._data.flush_recent_readings()

    def send_snap(self):
        snapshot = self._data.make_snapshot()
        self._send_to(self.atn, snapshot)
        if self.settings.admin.enabled:
            self._send_to(self.admin, snapshot)

    async def report_sending_task(self):
        while not self._stop_requested:
            try:
                if self.time_to_send_report():
                    self.send_report()
                    self._last_report_second = int(time.time())
                await asyncio.sleep(self.seconds_til_next_report())
            except Exception as e:
                self.log(e)

    async def snap_sending_task(self):
        while not self._stop_requested:
            try:
                if self.time_to_send_snap():
                    self.send_snap()
                    self._last_snap_s = int(time.time())
                await asyncio.sleep(self.seconds_til_next_snap())
            except Exception as e:
                self.log(e)

    #####################################################################
    # Basic plumbing - mostly about messages
    #####################################################################

    def _send_to(self, to_node: ShNode, payload: Any, from_node: ShNode = None) -> None:
        """Use this for primary_scada to send messages"""
        if to_node is None:
            return
        if from_node is None:
            from_node = self.node

        # HACK FOR nodes whose 'actors' are handled by their parent's communicator
        communicator_by_name = {to_node.Name: to_node.Name}
        communicator_by_name[H0N.home_alone_normal] = H0N.home_alone
    
        # if the message is meant for primary_scada, process here
        if to_node.name == self.name:
            self.process_scada_message(from_node, payload)
        
        # if its meant for an actor spawned by primary_scada (aka communicator)
        # call its process_message
        elif communicator_by_name[to_node.Name] in set(self._communicators.keys()):
            self.get_communicator(communicator_by_name[to_node.Name]).process_message(
                Message(Src=from_node.Name, Dst=to_node.Name, Payload=payload)
            )
        elif to_node.Name == H0N.admin:
            self._links.publish_message(
                link_name=self.ADMIN_MQTT,
                message=Message(
                    Src=self.publication_name, Dst=to_node.Name, Payload=payload
                ),
                qos=QOS.AtMostOnce,
            )
        elif to_node.Name == H0N.atn:
            #self._links.publish_upstream(payload)
            self._links.publish_message(
                link_name=self.ATN_MQTT,
                message=Message(
                    Src=self.publication_name, Dst=to_node.Name, Payload=payload
                ),
                qos=QOS.AtMostOnce,
            )
        else:  # publish to local for actors on LAN not run by primary_scada
            self._links.publish_message(
                link_name=Scada.LOCAL_MQTT,
                message=Message(Src=from_node.Name, Dst=to_node.Name, Payload=payload),
                qos=QOS.AtMostOnce,
                use_link_topic=True,
            )

    def _derived_process_message(self, message: Message):
        """Plumbing: messages received on the internal proactor queue

        Replaces proactor _derived_process_message. Either routes to the appropriate
        node or - if message is intended for primary scada - sends on to _process_my_message
        """
        from_node = self._layout.node(message.Header.Src, None)
        to_node = self._layout.node(message.Header.Dst, None)

        if to_node is not None and to_node != self.node:
            try:
                self._send_to(to_node, message.Payload, from_node)
            except Exception as e:
                print(f"Problem with message to {to_node.name}")
                print(f"message {message}")
                print(f"payload {message.Payload}")
                raise e
        else:
            self.process_scada_message(from_node=from_node, payload=message.Payload)

    def _derived_process_mqtt_message(
        self, message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:

        to_node = self._layout.node(message.Header.Dst, None)
        if to_node is None:
            to_node = self.node
        payload = decoded.Payload
        src = decoded.Header.Src
        if message.Payload.client_name == self.LOCAL_MQTT:
            # store and pass on all the events from scada2
            if isinstance(decoded.Payload, EventBase):
                self.generate_event(decoded.Payload)
                return
        elif message.Payload.client_name == self.ATN_MQTT:
            if src != self.layout.atn_g_node_alias:
                self.log(
                    f"IGNORING message from upstream. Expected {self.layout.atn_g_node_alias} but got {src}"
                )
                return
            src = H0N.atn
        elif message.Payload.client_name == self.ADMIN_MQTT:
            if not self.settings.admin.enabled:
                return
            src = H0N.admin
            # TODO: make admin conversation less hacky?
        else:
            raise ValueError(
                "ERROR. No mqtt handler for mqtt client %s", message.Payload.client_name
            )
        from_node = self._layout.node(src, None)

        if from_node is None:
            self.log(f"Got a message from unrecognized {decoded.Header.Src} - ignoring")
            self.decoded = decoded
            return

        self._send_to(to_node, payload, from_node)

    def init(self) -> None:
        """Called after constructor so derived functions can be used in setup."""

    @classmethod
    def make_event_persister(cls, settings: ScadaSettings) -> TimedRollingFilePersister:
        return TimedRollingFilePersister(
            settings.paths.event_dir,
            max_bytes=settings.persister.max_bytes,
            pat_watchdog_args=SystemDWatchdogCommandBuilder.pat_args(
                str(settings.paths.name)
            ),
        )

    def run_in_thread(self, daemon: bool = True) -> threading.Thread:
        """Basic function for running the scada"""

        async def _async_run_forever():
            try:
                await self.run_forever()

            finally:
                self.stop()

        def _run_forever():
            asyncio.run(_async_run_forever())

        thread = threading.Thread(target=_run_forever, daemon=daemon)
        thread.start()
        return thread

    #####################################################################
    # Admin related
    #####################################################################

    async def _timeout_admin(self, timeout_seconds: Optional[int] = None) -> None:
        if (
            timeout_seconds is None
            or timeout_seconds > self.settings.admin.max_timeout_seconds
        ):
            await asyncio.sleep(self.settings.admin.max_timeout_seconds)
        else:
            await asyncio.sleep(timeout_seconds)
        if self.top_state == TopState.Admin:
            self.admin_times_out()

    def _renew_admin_timeout(self, timeout_seconds: Optional[int] = None):
        if self._admin_timeout_task is not None:
            self._admin_timeout_task.cancel()
        self._admin_timeout_task = asyncio.create_task(
            self._timeout_admin(timeout_seconds)
        )

    def _forward_single_reading(self, reading: SingleReading) -> None:
        if (
            self.settings.admin.enabled
            and reading.ChannelName in self._layout.data_channels
        ):
            if (
                self._layout.node(
                    self._layout.data_channels[reading.ChannelName].AboutNodeName
                ).ActorClass
                == ActorClass.Relay
            ):
                self._send_to(self.admin, reading)

    #################################################
    # Various properties
    #################################################

    @property
    def name(self):
        return self._name

    @property
    def node(self) -> ShNode:
        return self._node

    @property
    def publication_name(self) -> str:
        return self._layout.scada_g_node_alias

    @property
    def subscription_name(self) -> str:
        return H0N.primary_scada

    @property
    def settings(self) -> ScadaSettings:
        return cast(ScadaSettings, self._settings)

    @property
    def hardware_layout(self) -> House0Layout:
        return self._layout

    @property
    def layout(self) -> House0Layout:
        return self._layout

    @property
    def admin(self) -> ShNode:
        return self.layout.node(H0N.admin)

    @property
    def atn(self) -> ShNode:
        return self.layout.node(H0N.atn)

    @property
    def atomic_ally(self) -> ShNode:
        return self.layout.node(H0N.atomic_ally)

    @property
    def home_alone(self) -> ShNode:
        return self.layout.node(H0N.home_alone)

    @property
    def relay_multiplexer(self) -> ShNode:
        return self.layout.node(H0N.relay_multiplexer)

    @property
    def zero_ten_out_multiplexer(self) -> ShNode:
        return self.layout.node(H0N.zero_ten_out_multiplexer)

    @property
    def synth_generator(self) -> ShNode:
        return self.layout.node(H0N.synth_generator)

    @property
    def hp_boss(self) -> ShNode:
        return self.layout.node(H0N.hp_boss)

    @property
    def sieg_loop(self) -> ShNode:
        return self.layout.node(H0N.sieg_loop)

    @property
    def pico_cycler(self) -> ShNode:
        return self.layout.node(H0N.pico_cycler)

    @property
    def data(self) -> ScadaData:
        return self._data

    @property
    def layout_lite(self) -> LayoutLite:
        tank_nodes = [
            node
            for node in self.layout.nodes.values()
            if node.ActorClass == ActorClass.ApiTankModule
        ]
        flow_nodes = [
            node
            for node in self.layout.nodes.values()
            if node.ActorClass == ActorClass.ApiFlowModule
        ]
        return LayoutLite(
            FromGNodeAlias=self.layout.scada_g_node_alias,
            FromGNodeInstanceId=self.layout.scada_g_node_id,
            Strategy=self.layout.flow_manifold_variant,
            ZoneList=self.layout.zone_list,
            TotalStoreTanks=self.layout.total_store_tanks,
            TankModuleComponents=[node.component.gt for node in tank_nodes],
            FlowModuleComponents=[node.component.gt for node in flow_nodes],
            ShNodes=[node.to_gt() for node in self.layout.nodes.values()],
            DataChannels=[ch.to_gt() for ch in self.layout.data_channels.values()],
            SynthChannels=[ch.to_gt() for ch in self.layout.synth_channels.values()],
            Ha1Params=self.data.ha1_params,
            I2cRelayComponent=self.layout.node(H0N.relay_multiplexer).component.gt,
            MessageCreatedMs=int(time.time() * 1000),
            MessageId=str(uuid.uuid4()),
        )

    ################################################
    # Hacky stuff
    ###############################################

    def update_env_variable(self, variable, new_value, testing: bool = False) -> None:
        """
        Updates .env with new Scada Params.
        TODO: move this somewhere else, like a local sqlite db
        """
        if testing:
            dotenv_filepath = dotenv.find_dotenv(usecwd=True)
            if not dotenv_filepath:
                self.logger.error("Couldn't find a .env file - perhaps because in CI?")
                return
        else:
            dotenv_filepath = "/home/pi/gridworks-scada/.env"
            if not os.path.isfile(dotenv_filepath):
                self.log("Did not find .env file")
                return
        with open(dotenv_filepath, "r") as file:
            lines = file.readlines()
        with open(dotenv_filepath, "w") as file:
            line_exists = False
            for line in lines:
                if line.replace(" ", "").startswith(f"{variable}="):
                    file.write(f"{variable}={new_value}\n")
                    line_exists = True
                else:
                    file.write(line)
            if not line_exists:
                file.write(f"\n{variable}={new_value}\n")

    def log(self, note: str) -> None:
        log_str = f"[scada] {note}"
        self.services.logger.error(log_str)

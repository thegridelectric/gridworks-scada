"""Scada implementation"""
import os
import asyncio
import enum
import uuid
import threading
import time
from typing import Any, List, Optional, cast

import dotenv
from transitions import Machine
from gwproto.message import Header
from gwproactor.external_watchdog import SystemDWatchdogCommandBuilder
from gwproactor.links import LinkManagerTransition
from gwproactor.links.link_settings import LinkSettings
from gwproactor.message import InternalShutdownMessage
from gwproto import create_message_model
from gwproto import MQTTTopic
from gwproto.enums import ActorClass

from actors.power_meter import PowerMeter
from data_classes.house_0_layout import House0Layout
from gwproto.messages import FsmAtomicReport, FsmFullReport
from gwproto.messages import EventBase
from gwproto.message import Message
from gwproto.messages import PowerWatts
from gwproto.messages import SendSnap

from gwproto.named_types import (AnalogDispatch, ChannelReadings, MachineStates,
                                SingleReading, SyncedReadings,
                                TicklistReedReport, TicklistHallReport)

from gwproto.messages import ReportEvent

from actors.api_flow_module import TicklistHall, TicklistReed
from gwproto import MQTTCodec
from result import Ok
from result import Result

from gwproactor import ActorInterface
from actors.api_tank_module import MicroVolts
from actors.scada_data import ScadaData
from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwproto.data_classes.sh_node import ShNode
from gwproactor import QOS

from gwproactor.links import Transition
from gwproactor.message import MQTTReceiptPayload
from gwproactor.persister import TimedRollingFilePersister
from gwproactor.proactor_implementation import Proactor

from data_classes.house_0_names import H0N
from drivers.power_meter.power_meter_driver import POWER_METER_LOGGER_NAME
from enums import MainAutoState, TopState
from named_types import (AdminDispatch, AdminKeepAlive, AdminReleaseControl, ChannelFlatlined, DispatchContractGoDormant,
                        DispatchContractGoLive, EnergyInstruction, FsmEvent, GameOn, Glitch, GoDormant, 
                        LayoutLite, NewCommandTree, PicoMissing, RemainingElec,  RemainingElecEvent,
                        ScadaParams, SendLayout, SingleMachineState, WakeUp, HeatingForecast)

ScadaMessageDecoder = create_message_model(
    "ScadaMessageDecoder", 
    [
        "named_types",
        "gwproto.messages",
        "gwproactor.message",
        "actors.message",
    ]
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
    GRIDWORKS_MQTT = "gridworks"
    LOCAL_MQTT = "local"
    ADMIN_MQTT = "admin"

    _data: ScadaData
    _last_report_second: int
    _last_sync_snap_s: int
    _dispatch_live_hack: bool
    _channels_reported: bool
    _layout_lite: LayoutLite
    _admin_timeout_task: Optional[asyncio.Task] = None

    top_states = ["Auto", "Admin"]
    top_transitions = [
        {"trigger": "AdminWakesUp", "source": "Auto", "dest": "Admin"},
        {"trigger": "AdminTimesOut", "source": "Admin", "dest": "Auto"},
        {"trigger": "AdminReleasesControl", "source": "Admin", "dest": "Auto"}
    ]

    main_auto_states = ["Atn", "HomeAlone", "Dormant"]
    main_auto_transitions = [
        {"trigger": "AtnLinkDead", "source": "Atn", "dest": "HomeAlone"},
        {"trigger": "AtnWantsControl", "source": "HomeAlone", "dest": "Atn"},
        {"trigger": "AutoGoesDormant", "source": "Atn", "dest": "Dormant"},
        {"trigger": "AutoGoesDormant", "source": "HomeAlone", "dest": "Dormant"},
        {"trigger": "AutoWakesUp", "source": "Dormant", "dest": "HomeAlone"},
        {"trigger": "AtnReleasesControl", "source": "Atn", "dest": "HomeAlone"}
    ]
    def __init__(
        self,
        name: str,
        settings: ScadaSettings,
        hardware_layout: House0Layout,
        actor_nodes: Optional[List[ShNode]] = None,
    ):
        if not isinstance(hardware_layout, House0Layout):
            raise Exception("Make sure to pass Hosue0Layout object as hardware_layout!")
        self.is_simulated = False
        self._layout: House0Layout = hardware_layout
        self._data = ScadaData(settings, hardware_layout)
        super().__init__(name=name, settings=settings, hardware_layout=hardware_layout)
        remote_actor_node_names = {node.name for node in self._layout.nodes.values() if
                   self._layout.parent_node(node) != self._node and
                   node != self._node and
                   node.has_actor}
        self._links.add_mqtt_link(
            LinkSettings(
                client_name=self.LOCAL_MQTT,
                gnode_name=H0N.secondary_scada,
                spaceheat_name=H0N.secondary_scada,
                mqtt=self.settings.local_mqtt,
                codec=LocalMQTTCodec(
                    primary_scada=True,
                    remote_node_names=remote_actor_node_names
                ),
                downstream=True,
            )
        )
        self._links.add_mqtt_link(
            LinkSettings(
                client_name=self.GRIDWORKS_MQTT,
                gnode_name=self._layout.atn_g_node_alias,
                spaceheat_name=H0N.atn,
                mqtt=self.settings.gridworks_mqtt,
                codec=GridworksMQTTCodec(self._layout),
                upstream=True,
            )
        )
        for node_name in remote_actor_node_names:
            self._links.subscribe(
                client=self.LOCAL_MQTT,
                topic=MQTTTopic.encode(
                    envelope_type=Message.type_name(),
                    src=node_name,
                    dst=self.subscription_name,
                    message_type="#",
                ),
                qos=QOS.AtMostOnce,
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
        self._last_sync_snap_s = int(now)
        self._dispatch_live_hack = False
        self.pending_dispatch: Optional[AnalogDispatch] = None
        self.logger.add_category_logger(
            POWER_METER_LOGGER_NAME,
            level=settings.power_meter_logging_level,
        )
        if actor_nodes is not None:
            for actor_node in actor_nodes:
                self.add_communicator(
                    ActorInterface.load(
                        actor_node.Name,
                        str(actor_node.actor_class),
                        self,
                        self.DEFAULT_ACTORS_MODULE
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
    def data(self) -> ScadaData:
        return self._data

    def _start_derived_tasks(self):
        self._tasks.append(
            asyncio.create_task(self.update_report(), name="update_report")
        )
        self._tasks.append(
            asyncio.create_task(self.update_snap(), name="update_snap")
        )
        self._tasks.append(
            asyncio.create_task(self.state_tracker(), name="scada top_state_tracker")
        )

    async def update_report(self):
        while not self._stop_requested:
            try:
                if self.time_to_send_snap():
                    self.send_snap()
                    self._last_sync_snap_s = int(time.time())
                if self.time_to_send_report():
                    self.send_report()
                    self._last_report_second = int(time.time())
                await asyncio.sleep(self.seconds_til_next_report())
            except Exception as e:
                try:
                    if not isinstance(e, asyncio.CancelledError):
                        self._logger.exception(e)
                        self._send(
                            InternalShutdownMessage(
                                Src=self.name,
                                Reason=(
                                    f"update_report() task got exception: <{type(e)}> {e}"
                                ),
                            )
                        )
                finally:
                    break
    
    async def update_snap(self):
        while not self._stop_requested:
            try:
                if self.time_to_send_snap():
                    self.send_snap()
                await asyncio.sleep(5)
            except Exception as e:
                try:
                    if not isinstance(e, asyncio.CancelledError):
                        self._logger.exception(e)
                        self._send(
                            InternalShutdownMessage(
                                Src=self.name,
                                Reason=(
                                    f"update_report() task got exception: <{type(e)}> {e}"
                                ),
                            )
                        )
                finally:
                    break

    @property
    def _layout_lite(self) -> LayoutLite:
        tank_nodes = [node for node in self.layout.nodes.values() if node.ActorClass == ActorClass.ApiTankModule]
        flow_nodes = [node for node in self.layout.nodes.values() if node.ActorClass == ActorClass.ApiFlowModule]
        return LayoutLite(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                FromGNodeInstanceId=self.layout.scada_g_node_id,
                Strategy=self.layout.strategy,
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

    def _send_layout_lite(self, link_name: str) -> None:
        self.publish_message(
            link_name,
            Message(
                Src=self.publication_name,
                Payload=self._layout_lite,
            )
        )

    def send_report(self):
        report = self._data.make_report(self._last_report_second)
        self._data.reports_to_store[report.Id] = report
        self.generate_event(ReportEvent(Report=report))
        self._publish_to_local(self._node, report)
        self._data.flush_recent_readings()
    
    def send_snap(self):
        snapshot = self._data.make_snapshot()
        self._publish_to_local(self._node, snapshot)
        self._links.publish_upstream(snapshot)
        if self.settings.admin.enabled:
            self._publish_to_link(self.ADMIN_MQTT, snapshot)

    def next_report_second(self) -> int:
        last_report_second_nominal = int(
            self._last_report_second
            - (self._last_report_second % self.settings.seconds_per_report)
        )
        return last_report_second_nominal + self.settings.seconds_per_report

    def next_sync_snap_s(self) -> int:
        last_sync_snap_s = int(
            self._last_sync_snap_s
            - (self._last_sync_snap_s % self.settings.seconds_per_snapshot)
        )
        return last_sync_snap_s + self.settings.seconds_per_snapshot

    def seconds_til_next_report(self) -> float:
        return self.next_report_second() - time.time()

    def time_to_send_report(self) -> bool:
        return time.time() > self.next_report_second()
    
    def time_to_send_snap(self) -> bool:
        if time.time() > self.next_sync_snap_s():
            self._last_sync_snap_s = int(time.time())
            return True
        #TODO: add sending on change.

    def _publish_to_link(self, link_name: str, payload: Any, qos: QOS = QOS.AtMostOnce):
        return self.publish_message(
            link_name,
            Message(
                Src=self.publication_name,
                Payload=payload
            ),
            qos=qos
        )

    def _publish_to_local(self, from_node: ShNode, payload, qos: QOS = QOS.AtMostOnce):
        message = Message(Src=from_node.Name, Payload=payload)
        return self._links.publish_message(Scada.LOCAL_MQTT, message, qos=qos)

    def _derived_process_message(self, message: Message):
        self._logger.path("++Scada._derived_process_message %s/%s", message.Header.Src, message.Header.MessageType)
        path_dbg = 0
        from_node = self._layout.node(message.Header.Src, None)
        match message.Payload:
            case Glitch():
                self._links.publish_upstream(message.Payload, QOS.AtMostOnce)
            case GameOn():
                try:
                    self._links.publish_upstream(message.Payload, QOS.AtMostOnce)
                except Exception as e:
                    self.logger.error(f"Problem with {message.Header}: {e}")
            case RemainingElec():
                try:
                    self.get_communicator(H0N.atomic_ally).process_message(message)
                    self.generate_event(RemainingElecEvent(Remaining=message.Payload))
                    self._publish_to_local(self._node, message.Payload)
                    self.log("Sent remaining elec to ATN")
                except Exception as e:
                    self.logger.error(f"Problem with {message.Header}: {e}")
            case PowerWatts():
                path_dbg |= 0x00000001
                if from_node is self._layout.power_meter_node:
                    path_dbg |= 0x00000002
                    self.power_watts_received(message.Payload)
                    self.get_communicator(H0N.synth_generator).process_message(message)
                else:
                    raise Exception(
                        f"message.Header.Src {message.Header.Src} must be from {self._layout.power_meter_node} for PowerWatts message"
                    )
            case AnalogDispatch():
                path_dbg |= 0x10000000
                try:
                    self.get_communicator(message.Header.Dst).process_message(message)
                except Exception as e:
                    self.logger.error(f"Problem with  {message.Header}: {e}")
            case ChannelFlatlined():
                self.data.flush_channel_from_latest(message.Payload.Channel.Name)
            case ChannelReadings():
                if message.Header.Dst == self.name:
                    path_dbg |= 0x00000004
                    try:
                        self.channel_readings_received(from_node, message.Payload)
                    except Exception as e:
                        self.logger.error(f"problem with channel_readings_received: \n {e}")
                        return
                else:
                    path_dbg |= 0x00000008
                    try:
                        self.get_communicator(message.Header.Dst).process_message(message)
                    except Exception as e:
                        self.logger.error(f"problem with {message}: \n{e}")
            case FsmAtomicReport():
                path_dbg |= 0x00000010
                self.get_communicator(message.Header.Dst).process_message(message)
            case FsmEvent():
                path_dbg |= 0x00000020
                self.get_communicator(message.Header.Dst).process_message(message)
            case FsmFullReport():
                path_dbg |= 0x00000040
                if message.Header.Dst == self.name:
                    path_dbg |= 0x00000080
                    self.fsm_full_report_received(message.Payload)
                else:
                    path_dbg |= 0x00000100
                    self.get_communicator(message.Header.Dst).process_message(message)
            case GoDormant():
                self.get_communicator(message.Header.Dst).process_message(message)
            case MachineStates():
                path_dbg |= 0x00000200
                self.machine_states_received(message.Payload)
            case MicroVolts():
                path_dbg |= 0x00000400
                self.get_communicator(message.Header.Dst).process_message(message)
            case NewCommandTree():
                self._links.publish_upstream(message.Payload, QOS.AtMostOnce)
            case PicoMissing():
                path_dbg |= 0x00000800
                self.get_communicator(message.Header.Dst).process_message(message)
            case SingleMachineState():
                self.single_machine_state_received(message.Payload)
            case SingleReading():
                path_dbg |= 0x00001000
                self.single_reading_received(message.Payload)
            case SyncedReadings():
                if message.Header.Dst == self.name:
                    path_dbg |= 0x00002000
                    self.synced_readings_received(
                            from_node, message.Payload
                        )
                else:
                    path_dbg |=  0x00004000
                    try:
                        self.get_communicator(message.Header.Dst).process_message(message)
                    except Exception as e:
                        self.logger.error(f"problem with {message}: \n{e}")
            case TicklistHall():
                path_dbg |= 0x00008000
                self.get_communicator(message.Header.Dst).process_message(message)
            case TicklistHallReport():
                path_dbg |= 0x00010000
                self._links.publish_upstream(message.Payload, QOS.AtMostOnce)
            case TicklistReed():
                path_dbg |= 0x00020000
                self.get_communicator(message.Header.Dst).process_message(message)
            case TicklistReedReport():
                path_dbg |= 0x00040000
                self._links.publish_upstream(message.Payload, QOS.AtMostOnce)
            case WakeUp():
                self.get_communicator(message.Header.Dst).process_message(message)
            case HeatingForecast():
                try:
                    self.get_communicator(H0N.atomic_ally).process_message(message)
                    self.get_communicator(H0N.home_alone).process_message(message)
                except Exception as e:
                    self.logger.error(f"Problem with {message.Header}: {e}")
            case _:
                raise ValueError(
                    f"There is no handler for message payload type [{type(message.Payload)}]"
                )
        self._logger.path("--Scada._derived_process_message  path:0x%08X", path_dbg)

    def _derived_process_mqtt_message(
        self, message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:
        self._logger.path("++Scada._derived_process_mqtt_message %s", message.Payload.message.topic)
        path_dbg = 0
        if message.Payload.client_name == self.LOCAL_MQTT:
            path_dbg |= 0x00000001
            self._process_downstream_mqtt_message(message, decoded)
        elif message.Payload.client_name == self.GRIDWORKS_MQTT:
            path_dbg |= 0x00000002
            self._process_upstream_mqtt_message(message, decoded)
        elif message.Payload.client_name == self.ADMIN_MQTT:
            path_dbg |= 0x00000004
            self._process_admin_mqtt_message(message, decoded)
        else:
            raise ValueError("ERROR. No mqtt handler for mqtt client %s", message.Payload.client_name)
        self._logger.path("--Scada._derived_process_mqtt_message  path:0x%08X", path_dbg)

    def _process_upstream_mqtt_message(
        self, message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:
        self._logger.path("++_process_upstream_mqtt_message %s", message.Payload.message.topic)
        path_dbg = 0
        match decoded.Payload:
            case AnalogDispatch():
                path_dbg |= 0x00000001
                self._analog_dispatch_received(decoded.Payload)
            case DispatchContractGoDormant():
                self.atn_releases_control(decoded.Payload)
            case DispatchContractGoLive():
                self.atn_wants_control(decoded.Payload)
            case EnergyInstruction():
                try:
                    self.get_communicator(H0N.synth_generator).process_message(decoded)
                except Exception as e:
                    self.logger.error(f"In SynthGenerator: Problem with {message.Header}: {e}")
                if self.auto_state == MainAutoState.Atn:
                    try:
                        self.get_communicator(H0N.atomic_ally).process_message(decoded)
                    except Exception as e:
                        self.logger.error(f"In AtomicAlly: Problem with {message.Header}: {e}")

            case SendLayout():
                path_dbg |= 0x00000004
                self._send_layout_lite(self.upstream_client)
            case SendSnap():
                path_dbg |= 0x00000008
                self._send_snap_received(decoded.Payload)
            case ScadaParams():
                path_dbg |= 0x00000010
                self._scada_params_received(decoded.Payload)
                self.get_communicator(H0N.synth_generator).process_message(decoded)
            case _:
                # Intentionally ignore this for forward compatibility
                path_dbg |= 0x00000020
        self._logger.path("--_process_upstream_mqtt_message  path:0x%08X", path_dbg)

    def _process_downstream_mqtt_message(
            self, message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:
        self._logger.path("++_process_downstream_mqtt_message %s", message.Payload.message.topic)
        path_dbg = 0
        match decoded.Payload:
            case EventBase():
                path_dbg |= 0x00000001
                self.generate_event(decoded.Payload)
            case SyncedReadings():
                path_dbg |= 0x00000002
                try:
                    self.synced_readings_received(
                        self._layout.node(decoded.Header.Src),
                        decoded.Payload
                    )
                except Exception as e:
                    #TODO - consider sending an Alert or ProbemEvent
                    self.logger.error(f"Failed to process SyncedReading from scada2!: {e}")
            case _:
                # Intentionally ignore this for forward compatibility
                path_dbg |= 0x00000004
        self._logger.path("--_process_downstream_mqtt_message  path:0x%08X", path_dbg)

    def _process_admin_mqtt_message(
            self, message: Message[MQTTReceiptPayload], decoded: Message[Any]
    ) -> None:
        self._logger.path("++_process_admin_mqtt_message %s", message.Payload.message.topic)
        path_dbg = 0
        if self.settings.admin.enabled:
            path_dbg |= 0x00000001
            match decoded.Payload:
                case AdminDispatch():
                    path_dbg |= 0x00000001
                    if not self.top_state == TopState.Admin:
                        self.admin_wakes_up()
                        self.log('Admin Wakes Up')
                    self._renew_admin_timeout(timeout_seconds=decoded.Payload.TimeoutSeconds)
                    event = decoded.Payload.DispatchTrigger
                    self.log(f"AdminDispatch event toype name is {event.TypeName}")
                    if communicator := self.get_communicator(event.ToHandle.split('.')[-1]):
                        path_dbg |= 0x00000010
                        communicator.process_message(
                            Message(
                                header=Header(
                                    Src=H0N.admin,
                                    Dst=communicator.name,
                                    MessageType=event.TypeName,
                                ),
                                Payload=event
                            )
                        )
                case SendLayout():
                    path_dbg |= 0x00000002
                    self._publish_to_link(self.ADMIN_MQTT, self._layout_lite)
                case SendSnap():
                    path_dbg |= 0x00000004
                    self._publish_to_link(self.ADMIN_MQTT, self._data.make_snapshot())
                # TODO: remove when not maintaining backwards compatability for this
                case FsmEvent() as event:
                    path_dbg |= 0x00000008
                    if self.top_state != TopState.Admin:
                        # change control
                        self.admin_wakes_up()
                    if communicator := self.get_communicator(event.ToHandle.split('.')[-1]):
                        path_dbg |= 0x00000010
                        communicator.process_message(
                            Message(
                                header=Header(
                                    Src=H0N.admin,
                                    Dst=communicator.name,
                                    MessageType=decoded.Payload.TypeName,
                                ),
                                Payload=decoded.Payload
                            )
                        )
                case AdminKeepAlive():
                    path_dbg |= 0x00000020
                    self._renew_admin_timeout(timeout_seconds=decoded.Payload.AdminTimeoutSeconds)
                    self.log(f'Admin timeout renewed: {decoded.Payload.AdminTimeoutSeconds} seconds')
                    if not self.top_state == TopState.Admin:
                        self.admin_wakes_up()
                        self.log('Admin Wakes Up')
                case AdminReleaseControl():
                    path_dbg |= 0x00000040
                    if self.top_state == TopState.Admin:
                        self.admin_releases_control()
                case _:
                    # Intentionally ignore this for forward compatibility
                    path_dbg |= 0x00000080
        self._logger.path("--_process_admin_mqtt_message  path:0x%08X", path_dbg)
    
    async def _timeout_admin(self, timeout_seconds: Optional[int] = None) -> None:
        if timeout_seconds is None or timeout_seconds>self.settings.admin.max_timeout_seconds:
            await asyncio.sleep(self.settings.admin.max_timeout_seconds)
        else:
            await asyncio.sleep(timeout_seconds)
        if self.top_state == TopState.Admin:
            self.admin_times_out()
    
    def _renew_admin_timeout(self, timeout_seconds: Optional[int] = None):
        if self._admin_timeout_task is not None:
            self._admin_timeout_task.cancel()
        self._admin_timeout_task = asyncio.create_task(self._timeout_admin(timeout_seconds))

    def update_env_variable(self, variable, new_value, testing:bool=False) -> None:
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
            dotenv_filepath = "/home/pi/gw-scada-spaceheat-python/.env"
            if not os.path.isfile(dotenv_filepath):
                self.log("Did not find .env file")
                return
        with open(dotenv_filepath, 'r') as file:
            lines = file.readlines()
        with open(dotenv_filepath, 'w') as file:
            line_exists = False
            for line in lines:
                if line.replace(' ','').startswith(f"{variable}="):
                    file.write(f"{variable}={new_value}\n")
                    line_exists = True      
                else:
                    file.write(line)
            if not line_exists:
                file.write(f"\n{variable}={new_value}\n")

    def _scada_params_received(self, message: ScadaParams, testing:bool=False) -> None:
        if message.FromGNodeAlias != self.hardware_layout.atn_g_node_alias:
            return
        new = message.NewParams
        if new:
            old = self.data.ha1_params
            self.data.ha1_params = new
            if new.AlphaTimes10 != old.AlphaTimes10:          
                self.update_env_variable('SCADA_ALPHA', new.AlphaTimes10 / 10, testing)
            if new.BetaTimes100 != old.BetaTimes100:
                self.update_env_variable('SCADA_BETA', new.BetaTimes100 / 100, testing)
            if new.GammaEx6 != old.GammaEx6:
                self.update_env_variable('SCADA_GAMMA', new.GammaEx6 / 1e6, testing)
            if new.IntermediatePowerKw != old.IntermediatePowerKw:
                self.update_env_variable('SCADA_INTERMEDIATE_POWER', new.IntermediatePowerKw, testing)
            if new.IntermediateRswtF != old.IntermediateRswtF:
                self.update_env_variable('SCADA_INTERMEDIATE_RSWT', new.IntermediateRswtF, testing)
            if new.DdPowerKw != old.DdPowerKw:
                self.update_env_variable('SCADA_DD_POWER', new.DdPowerKw, testing)
            if new.DdRswtF != old.DdRswtF:
                self.update_env_variable('SCADA_DD_RSWT', new.DdRswtF, testing)
            if new.DdDeltaTF != old.DdDeltaTF:
                self.update_env_variable('SCADA_DD_DELTA_T', new.DdDeltaTF, testing)
            if new.LoadOverestimationPercent != old.LoadOverestimationPercent:
                self.update_env_variable('SCADA_LOAD_OVERESTIMATION_PERCENT', new.LoadOverestimationPercent, testing)


            response = ScadaParams(
                    FromGNodeAlias=self.hardware_layout.scada_g_node_alias,
                    FromName=self.name,
                    ToName=message.FromName,
                    UnixTimeMs=int(time.time() * 1000),
                    MessageId=message.MessageId,
                    NewParams=self.data.ha1_params,
                    OldParams=old,
                )
            self.logger.error(f"Sending back {response}")
            self._links.publish_upstream(response)

    def _send_snap_received(self, payload: SendSnap):
        if payload.FromGNodeAlias != self._layout.atn_g_node_alias:
            return
        self._links.publish_upstream(self._data.make_snapshot())

    def power_watts_received(self, payload: PowerWatts):
        """The highest priority of the SCADA, from the perspective of the electric grid,
        is to report power changes as quickly as possible (i.e. milliseconds matter) on
        any asynchronous change more than x% (probably 2%).

        There is a single meter measuring all power getting reported - this is in fact
        what is Atomic (i.e. cannot be divided further) about the AtomicTNode. The
        asynchronous change calculation is already made in the power meter code. This
        function just passes through the result.

        The allocation to separate metered nodes is done ex-poste using the multipurpose
        telemetry data."""

        self._links.publish_upstream(payload, QOS.AtMostOnce)
        self._data.latest_total_power_w = payload.Watts
    
    def machine_states_received(self, payload: MachineStates) -> None:
        if payload.MachineHandle in self._data.recent_machine_states:
            prev: MachineStates = self._data.recent_machine_states[payload.MachineHandle]
            if payload.StateEnum != prev.StateEnum:
                raise Exception(f"{payload.MachineHandle} has conflicting state machines!"
                                f"{payload.StateEnum} and {prev.StateEnum}")
            
            self._data.recent_machine_states[payload.MachineHandle] =  MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                UnixMsList=prev.UnixMsList + payload.UnixMsList,
                StateList=prev.StateList + payload.StateList,
            )
        else:
            self._data.recent_machine_states[payload.MachineHandle] = payload
            
    def fsm_full_report_received(self, payload: FsmFullReport) -> None:
        self._data.recent_fsm_reports[payload.TriggerId] = payload

    def _forward_single_reading(self, reading: SingleReading) -> None:
        if (self.settings.admin.enabled
            and reading.ChannelName in self._layout.data_channels
        ):
            if self._layout.node(
                self._layout.data_channels[reading.ChannelName].AboutNodeName
            ).ActorClass== ActorClass.Relay:
                self._publish_to_link(self.ADMIN_MQTT, reading)

    def single_reading_received(self, payload: SingleReading) -> None:
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

    def single_machine_state_received(self, payload: SingleMachineState) -> None:
        if payload.MachineHandle in self._data.recent_machine_states:
            prev: MachineStates = self._data.recent_machine_states[payload.MachineHandle]
            if payload.StateEnum != prev.StateEnum:
                raise Exception(f"{payload.MachineHandle} has conflicting state machines!"
                                f"{payload.StateEnum} and {prev.StateEnum}")
            self._data.recent_machine_states[payload.MachineHandle] =  MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                UnixMsList=prev.UnixMsList + [payload.UnixMs],
                StateList=prev.StateList + [payload.State]
            )
        else:
            self._data.recent_machine_states[payload.MachineHandle] = MachineStates(
                MachineHandle=payload.MachineHandle,
                StateEnum=payload.StateEnum,
                StateList=[payload.State],
                UnixMsList=[payload.UnixMs]
            )

    def synced_readings_received(
        self, from_node: ShNode, payload: SyncedReadings
    ):
        self._logger.path(
            "++synced_readings_received from: %s  channels: %d",
            from_node.Name,
            len(payload.ChannelNameList)
        )
        path_dbg = 0
        for idx, channel_name in enumerate(payload.ChannelNameList):
            path_dbg |= 0x00000001
            if channel_name not in self._layout.data_channels:
                raise ValueError(
                    f"Name {channel_name} in payload.SyncedReadings not a recognized Data Channel!"
                )
            ch = self._layout.data_channels[channel_name]
            self._data.recent_channel_values[ch.Name].append(
                payload.ValueList[idx]
            )
            self._data.recent_channel_unix_ms[
                ch.Name
            ].append(payload.ScadaReadTimeUnixMs)
            self._data.latest_channel_values[ch.Name] = payload.ValueList[idx]
            self._data.latest_channel_unix_ms[ch.Name] = payload.ScadaReadTimeUnixMs
        self._logger.path(
            "--gt_sh_telemetry_from_multipurpose_sensor_received  path:0x%08X", path_dbg
        )
    
    def channel_readings_received(
            self, from_node: ShNode, payload: ChannelReadings
    ) -> None:
        self._logger.path(
            "++channel_readings_received for channel: %d",
            payload.ChannelName
        )
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
            self._data.latest_channel_unix_ms[ch.Name] = payload.ScadaReadTimeUnixMsList[-1]

    def _send_to(self, dst: ShNode, payload: Any) -> None:
        message = Message(Src=self.name, Dst=dst.name,Payload=payload)
        if dst.name in set(self._communicators.keys()) | {self.name}:
            self.send(message)
        elif dst.Name == H0N.admin:
            self._links.publish_message(self.ADMIN_MQTT, message)
        elif dst.Name == H0N.atn:
            self._links.publish_upstream(payload)
        else:
            self._links.publish_message(self.LOCAL_MQTT, message)
          
    def run_in_thread(self, daemon: bool = True) -> threading.Thread:
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
    # State Machine related
    #####################################################################

    # Top States: Admin, Auto
    # Top Events: AdminWakesUp, AdminTimesOut, AdminReleasesControl

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
        self.auto_goes_dormant()

    def admin_releases_control(self) -> None:
        if self.top_state != TopState.Admin:
            self.log("Ignoring AdminWakesUp, TopState not Admin")
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

    def auto_wakes_up(self) -> None:
        if self.auto_state !=MainAutoState.Dormant:
            self.log(f"STRANGE!! auto state is already{self.auto_state}")
            return

        # Trigger AutoWakesUp for auto state: Dormant -> HomeAlone
        self.AutoWakesUp()
        # all actuators report directly to home alone
        self.set_home_alone_command_tree()
        # Let homealone and pico-cycler know they in charge again
        self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
        self._send_to(self.layout.pico_cycler,WakeUp(ToName=H0N.pico_cycler) )

    def auto_goes_dormant(self) -> None:
        self._dispatch_live_hack = False
        if self.auto_state == MainAutoState.Dormant:
            self.log("Ignoring AutoGoesDormant ... auto state is already dormant")
            return
        # Trigger AutoGoesDormant for auto state: Atn OR HomeAlone -> Dormant 
        self.AutoGoesDormant()
        self.log(f"auto_state {self.auto_state}")
        # ADMIN CONTROL FOREST: a single tree, controlling all actuators
        self.set_admin_command_tree()
        
        # Let the active nodes know they've lost control of their actuators
        for direct_report in [self.layout.atomic_ally, self.layout.home_alone , self.layout.pico_cycler]:
            self._send_to(direct_report, GoDormant(FromName=self.name, ToName=direct_report.Name))
    
    def atn_releases_control(self, t: DispatchContractGoDormant) -> None:
        if t.FromGNodeAlias != self.layout.atn_g_node_alias:
            self.log(f"HUH? Message from {t.FromGNodeAlias}")
            return
        if self.auto_state != MainAutoState.Atn:
            self.log(f"Ignoring control request from atn, auto_state: {self.auto_state}")
            return
        self.AtnReleasesControl()
        self.set_home_alone_command_tree()
        self._dispatch_live_hack = False
        self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
        self._send_to(self.layout.atomic_ally, GoDormant(FromName=self.name, ToName=H0N.atomic_ally))
        
    def atn_wants_control(self, t: DispatchContractGoLive) -> None:
        if t.FromGNodeAlias != self.layout.atn_g_node_alias:
            self.log(f"HUH? Message from {t.FromGNodeAlias}")
            return
        if self.auto_state != MainAutoState.HomeAlone:
            self.log(f"Ignoring control request from atn, auto_state: {self.auto_state}")
            return
        
        # Trigger AtnWantsControl for auto state: HomeAlone -> Atn
        self.AtnWantsControl()
        self.log(f"AtnWantsControl! Auto state {self.auto_state}")
        # ATN CONTROL FOREST: pico cycler its own tree. All other actuators report to Atomic
        # Ally which reports to atn.
        self.set_atn_command_tree()
        
        # Set the hack dispatch contract to True... will take this out shortly
        self._dispatch_live_hack = True
        # Let homealone know its dormant:
        self._send_to(self.layout.home_alone, GoDormant(FromName=self.name, ToName=H0N.home_alone))
        # Let the atomic ally know its live
        self._send_to(self.layout.atomic_ally, WakeUp(ToName=H0N.atomic_ally))

    def atn_link_dead(self) -> None:
        if self.auto_state != MainAutoState.Atn:
            self.log(f"Atn link is dead, but we were in state {self.auto_state} anyway")
            return
        
        # Trigger AtnLinkDead auto state:  Atn -> HomeAlone
        self.AtnLinkDead()
        self.log(f"AtnLink id dead! Auto state {self.auto_state}")
        self._dispatch_live_hack = False
        self.set_home_alone_command_tree()
        # Let home alone know its in charge
        self._send_to(self.layout.home_alone, WakeUp(ToName=H0N.home_alone))
        self._send_to(self.layout.atomic_ally, GoDormant(FromName=H0N.primary_scada, ToName=H0N.atomic_ally))
        # Pico Cycler shouldn't change

    def _derived_recv_deactivated(self, transition: LinkManagerTransition) -> Result[bool, BaseException]:
        if transition.link_name == self.upstream_client:
            # proactor-speak for Atn is no longer talking with Scada, as evidenced
            # by the once-a-minute pings disappearing
            self.atn_link_dead()
        return Ok()

    def _derived_recv_activated(self, transition: Transition) -> Result[bool, BaseException]:
        if transition.link_name == self.upstream_client:
            self._send_layout_lite(transition.link_name)
        return Ok()

    def _analog_dispatch_received(self, dispatch: AnalogDispatch) -> None:
        self.logger.error("Got Analog Dispatch in SCADA!")
        if dispatch.FromGNodeAlias != self._layout.atn_g_node_alias:
            self.logger.error("IGNORING DISPATCH - NOT FROM MY ATN")
            return
        to_node = self.layout.node_by_handle(dispatch.ToHandle)
        if to_node:
            self.get_communicator(to_node.name).process_message(dispatch)
        # if self.top_state == TopState.Admin:
        #     to_node = self.layout.node_by_handle(dispatch.ToHandle)
        #     if to_node:
        #         self.get_communicator(to_node.name).process_message(dispatch)
        # elif self.top_state == TopState.Auto:
        #     self.pending_dispatch = dispatch
        #     # AdminWakesUp: Auto -> ChangingToAdmin
        #     self.AdminWakesUp()

        #     for node in self.layout.direct_reports(self.layout.auto_node):
        #         self._send_to(node, GoDormant(
        #             FromName=H0N.auto, 
        #             ToName=node.name,
        #             TriggerId=dispatch.TriggerId))
        # #TODO: if MainAutoState is not atn, ignore
    
    ###########################################################
    # Command Trees - the handles of the Spaceheat Nodes form a tree
    # where the line of direct report is required for following a command
    ##########################################################

    def set_home_alone_command_tree(self) -> None:
        #HOMEALONE CONTROL FOREST. Direct reports are pico cycler and home alone
        for node in self.layout.actuators:
            if node.Name == H0N.vdc_relay:
                node.Handle = f"{H0N.auto}.{H0N.pico_cycler}.{node.Name}"
            else:
                node.Handle = f"{H0N.auto}.{H0N.home_alone}.{H0N.home_alone_normal}.{node.Name}"
        self._links.publish_upstream(
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            )
        )

    def set_admin_command_tree(self) -> None:
        # ADMIN CONTROL FOREST. All actuators report directly to admin
        for node in self.layout.actuators:
            node.Handle = f"{H0N.admin}.{node.Name}"
        self._links.publish_upstream(
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            )
        )
    
    def set_atn_command_tree(self) -> None:
        for node in self.layout.actuators:
            if node.Name == H0N.vdc_relay:
                node.Handle = f"{H0N.auto}.{H0N.pico_cycler}.{node.Name}"
            else:
                node.Handle = f"{H0N.atn}.{H0N.atomic_ally}.{node.Name}"
        self._links.publish_upstream(
            NewCommandTree(
                FromGNodeAlias=self.layout.scada_g_node_alias,
                ShNodes=list(self.layout.nodes.values()),
                UnixMs=int(time.time() * 1000),
            )
        )

    async def state_tracker(self) -> None:
        loop_s = self.settings.seconds_per_report
        while True:
            hiccup = 1.5
            sleep_s = max(
                hiccup, loop_s - (time.time() % loop_s) - 1.2
            )
            await asyncio.sleep(sleep_s)
            # report the state
            if sleep_s != hiccup:
                self.machine_states_received(
                    MachineStates(
                        MachineHandle=self.node.handle,
                        StateEnum=TopState.enum_name(),
                        StateList=[self.top_state],
                        UnixMsList=[int(time.time() * 1000)],
                    ),
                )

                self.machine_states_received(
                    MachineStates(
                        MachineHandle=self.layout.auto_node.handle,
                        StateEnum=MainAutoState.enum_name(),
                        StateList=[self.auto_state],
                        UnixMsList=[int(time.time() * 1000)],
                    ),
                )
                self.logger.warning(f"Top state: {self.top_state}")
                self.logger.warning(f"Auto state: {self.auto_state}")

    @property
    def slow_dispatch_live(self):
        """
        ORIGINAL VISION (aka WHAT I WOULD HAVE GIVEN MY EYE TEETH
        FOR BACK AT VCHARGE)

         False if:
           - interactive polling between atn and scada is down [TESTING]
           - Scada sends notification that it is switching to home alone, and
           received an application-level (as opposed to say broker-level) ack
           - Atn requests that Scada take local control and Scada has agreed
           - scada sends "turn on" and power is not at 80% of max within 5 minutes
             and/or total charge for the market slot is not within 10% of projected
           - Fast more like:
                - scada sent dispatch command with more than 6 seconds; and
             before response as measured by power meter (requires a lot of clarification)
                -average time for response to dispatch commands in last 50 dispatches
             exceeds 3 seconds
           - Scada has not sent in daily attestion that power metering is
             working and accurate
           - no contract exists [i.e. ]


           Otherwise True

           Note that typically, the contract will not be alive because of house to
           cloud comms failure. But not always. There will be significant and important
           times (like when testing home alone perforamance) where we will want to send
           status messages etc up to the cloud even when the dispatch contract is not
           alive.
        """
        if self.auto_state == "Atn":
            if not self._dispatch_live_hack:
                raise Exception("WTF. _dispatch_live_hack False but auto_state is Atn ")
            return True
        else:
            if self._dispatch_live_hack:
                raise Exception(f"WTF. _dispatch_live_hack True but auto_state is {self._auto_state}")
            return False
    
    def log(self, note: str) ->None:
        log_str = f"[scada] {note}"
        self.services.logger.error(log_str)

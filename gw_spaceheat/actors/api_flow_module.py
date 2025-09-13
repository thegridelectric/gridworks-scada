import asyncio
import json
import time
from functools import cached_property
from typing import List, Literal, Optional, Sequence

import numpy as np
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gw.errors import DcError
from gwproactor import MonitoredName, Problems, AppInterface
from gwproactor.message import InternalShutdownMessage, PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.components import PicoFlowModuleComponent
from gwsproto.data_classes.house_0_names import H0N
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import GpmFromHzMethod, HzCalcMethod, MakeModel, TelemetryName
from gwproto.messages import ProblemEvent
from gwproto.named_types import (
    ChannelReadings,
    SyncedReadings,
    TicklistHall,
    TicklistHallReport,
    TicklistReed,
    TicklistReedReport,
)
from gwproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from actors.scada_actor import ScadaActor
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch, PicoMissing
from pydantic import BaseModel
from result import Ok, Result
from drivers.pipe_flow_sensor.signal_processing import butter_lowpass, filtering


FLATLINE_REPORT_S = 60


class FlowHallParams(BaseModel):
    HwUid: str
    ActorNodeName: str
    FlowNodeName: str
    PublishTicklistPeriodS: int
    PublishEmptyTicklistAfterS: int
    TypeName: Literal["flow.hall.params"] = "flow.hall.params"
    Version: Literal["101"] = "101"


class FlowReedParams(BaseModel):
    HwUid: str
    ActorNodeName: str
    FlowNodeName: str
    PublishTicklistLength: int
    PublishAnyTicklistAfterS: int
    DeadbandMilliseconds: int
    TypeName: Literal["flow.reed.params"] = "flow.reed.params"
    Version: Literal["101"] = "101"


class ApiFlowModule(ScadaActor):
    _stop_requested: bool
    _component: PicoFlowModuleComponent
    # last_heard: float
    # latest_gpm: float
    # latest_hz: float

    def __init__(
        self,
        name: str,
        services: AppInterface,
    ):
        super().__init__(name, services)
        component = services.hardware_layout.component(name)
        if not isinstance(component, PicoFlowModuleComponent):
            display_name = getattr(
                component.gt, "display_name", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> has type {type(component)}. "
                f"Expected PicoComponent.\n"
                f"  Node: {self.name}\n"
                f"  Component id: {component.gt.ComponentId}"
            )
        self._stop_requested: bool = False
        self._component = component
        self.hw_uid = self._component.gt.HwUid

        # Flow processing
        self.gpm_channel = self.layout.data_channels[f"{self.name}"]
        self.hz_channel = self.layout.data_channels[f"{self.name}-hz"]

        self.nano_timestamps: List[int] = []
        self.latest_tick_ns = None
        self.latest_hz = None
        self.latest_gpm = None

        self.capture_s = self._component.gt.ConfigList[0].CapturePeriodS
        self.latest_sync_send_s = time.time()
        self.last_heard = time.time()
        self.last_error_report = time.time()

        self.slow_turner: bool = False
        if self._component.gt.ConstantGallonsPerTick > 0.5:
            self.slow_turner = True

        self.validate_config_params()

        if self._component.gt.Enabled:
            if self._component.cac.MakeModel == MakeModel.GRIDWORKS__PICOFLOWHALL:
                self._services.add_web_route(
                    server_name=DEFAULT_WEB_SERVER_NAME,
                    method="POST",
                    path="/" + self.hall_params_path,
                    handler=self._handle_hall_params_post,
                )
                self._services.add_web_route(
                    server_name=DEFAULT_WEB_SERVER_NAME,
                    method="POST",
                    path="/" + self.ticklist_hall_path,
                    handler=self._handle_ticklist_hall_post,
                )
            elif self._component.cac.MakeModel == MakeModel.GRIDWORKS__PICOFLOWREED:
                self._services.add_web_route(
                    server_name=DEFAULT_WEB_SERVER_NAME,
                    method="POST",
                    path="/" + self.reed_params_path,
                    handler=self._handle_reed_params_post,
                )
                self._services.add_web_route(
                    server_name=DEFAULT_WEB_SERVER_NAME,
                    method="POST",
                    path="/" + self.ticklist_reed_path,
                    handler=self._handle_ticklist_reed_post,
                )
            else:
                raise Exception(
                    f"ApiFlowMeter actor does not recognize {self._component.cac.MakeModel}"
                )

    def validate_config_params(self) -> None:
        if self._component.gt.HzCalcMethod == HzCalcMethod.BasicExpWeightedAvg:
            if self._component.gt.ExpAlpha is None:
                raise DcError(f"{self.name}: BasicExpWeightedAvg requires ExpAlpha")
        if self._component.gt.HzCalcMethod == HzCalcMethod.BasicButterWorth:
            if self._component.gt.CutoffFrequency is None:
                raise DcError(f"{self.name}: BasicButterWorth requires CutoffFrequency")
        channel_names = [x.ChannelName for x in self._component.gt.ConfigList]
        if self.gpm_channel.Name not in channel_names:
            raise DcError(f"Missing {self.gpm_channel.Name} channel!")
        if self._component.gt.SendHz:
            if self.hz_channel.Name not in channel_names:
                raise DcError(f"SendHz but missing {self.hz_channel.Name}!")
        if self._component.gt.SendGallons:
            raise ValueError("Not set up to send gallons right now")

    @property
    def last_sync_s(self) -> int:
        '''Rounds down self.latest_sync_send_s to the nearest multiple of self.capture_s'''
        last_sync_s = self.latest_sync_send_s - (
            (self.latest_sync_send_s + 1) % self.capture_s
        )
        return int(last_sync_s)

    @property
    def next_sync_s(self) -> int:
        return self.last_sync_s + self.capture_s

    def sync_reading_sleep(self) -> int:
        if self.capture_s <= self.flatline_seconds():
            return 1
        if (time.time() - self.last_sync_s) > self.flatline_seconds():
            return self.flatline_seconds()
        else:
            return 1

    def publish_synced_readings(self):
        if self.latest_gpm is not None:
            channel_names = [self.gpm_channel.Name]
            values = [int(self.latest_gpm * 100)]
            if self._component.gt.SendHz:
                channel_names.append(self.hz_channel.Name)
                values.append(int(self.latest_hz * 1e6))
            self._send_to(
                self.primary_scada,
                SyncedReadings(
                    ChannelNameList=channel_names,
                    ValueList=values,
                    ScadaReadTimeUnixMs=int(time.time() * 1000),
                ),
            )

    def flatline_seconds(self) -> int:
        if self._component.cac.MakeModel == MakeModel.GRIDWORKS__PICOFLOWHALL:
            return self._component.gt.PublishEmptyTicklistAfterS * 2.5
        if self._component.cac.MakeModel == MakeModel.GRIDWORKS__PICOFLOWREED:
            return self._component.gt.PublishAnyTicklistAfterS * 2.5

    # This registers ApiFlowModule with the watchdog.
    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.flatline_seconds() * 2.1)]

    async def main(self):
        if self.slow_turner:
            self.publish_zero_flow()

        while not self._stop_requested:
            '''
            Checks if the pico flatlined
            Publishes readings synchronously every capture_s
            
            This loop happens either every flatline_seconds or every second (see sync_reading_sleep):
            If capture_s < flatline_seconds: 
                => Readings need to be synchronously captured more frequently than flatline seconds 
                => This loop runs every second
            If time since last synced readings were published > flatline_seconds: 
                => This loop runs every flatline_seconds
            In any other case: this loop runs every second
            '''

            self._send(PatInternalWatchdogMessage(src=self.name))

            # Check if flatlined, if so send an error report every FLATLINE_REPORT_S
            if (
                time.time() - self.last_heard > self.flatline_seconds() and
                time.time() - self.last_error_report > FLATLINE_REPORT_S
                ):
                self.latest_gpm = None
                self.latest_hz = None
                self._send_to(
                    self.pico_cycler,
                    PicoMissing(
                        ActorName=self.name,
                        PicoHwUid=self.hw_uid,
                    ),
                )
                self.last_error_report = time.time()

            try:
                # Publish readings synchronously every capture_s
                if time.time() > self.next_sync_s:
                    self.publish_synced_readings()
                    self.latest_sync_send_s = int(time.time())

                # Sleep
                await asyncio.sleep(self.sync_reading_sleep())

            except Exception as e:
                try:
                    if not isinstance(e, asyncio.CancelledError):
                        self.log(e)
                        self._send(
                            InternalShutdownMessage(
                                Src=self.name,
                                Reason=(f"update_flow_sync_readings() task got exception: <{type(e)}> {e}"),
                            )
                        )
                finally:
                    break

    @cached_property
    def hall_params_path(self) -> str:
        return f"{self.name}/flow-hall-params"

    @cached_property
    def reed_params_path(self) -> str:
        return f"{self.name}/flow-reed-params"

    @cached_property
    def ticklist_hall_path(self) -> str:
        return f"{self.name}/ticklist-hall"

    @cached_property
    def ticklist_reed_path(self) -> str:
        return f"{self.name}/ticklist-reed"

    async def _get_text(self, request: Request) -> Optional[str]:
        try:
            return await request.text()
        except Exception as e:
            self.services.send_threadsafe(
                Message(
                    Payload=Problems(
                        errors=[e]
                    ).problem_event(
                        summary=(
                            f"ERROR awaiting post ext <{self.name}>: {type(e)} <{e}>"
                        ),
                    )
                )
            )
        return None

    def _report_post_error(self, exception: BaseException, text: str) -> None:
        self.services.send_threadsafe(
            Message(
                Payload=Problems(
                    msg=f"request: <{text}>", errors=[exception]
                ).problem_event(
                    summary=(
                        f"Pico POST processing error for <{self._name}>: {type(exception)} <{exception}>"
                    ),
                )
            )
        )

    def need_to_update_layout(self) -> bool:
        if self._component.gt.HwUid:
            return False
        return True

    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoRelated] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)

    async def _handle_hall_params_post(self, request: Request) -> Response:
        # Read params as FlowHallParams
        text = await self._get_text(request)
        self.params_text = text
        try:
            params = FlowHallParams(**json.loads(text))
        except BaseException as e:
            self._report_post_error(e, "malformed FlowHall parameters!")
            self.log("Flow module params are malformed")
            return Response()
        if params.FlowNodeName != self._component.gt.FlowNodeName:
            self.log("FlowNodeName is not correct")
            return Response()
        if self._component.cac.MakeModel != MakeModel.GRIDWORKS__PICOFLOWHALL:
            raise Exception(
                f"{self.name} has {self._component.cac.MakeModel} but got FlowHallParams!"
            )
        self.pico_state_log(f"{params.HwUid} PARAMS")
        # Temporary hack prior to installerapp
        # Case where a Pico gets installed and the hardware layout does not have its id yet
        if self._component.gt.HwUid is None or self._component.gt.HwUid == params.HwUid:
            if self._component.gt.HwUid is None:
                self.log(f"UPDATE LAYOUT!!: Pico HWUID {params.HwUid}")
                self.hw_uid = params.HwUid
            new_params = FlowHallParams(
                HwUid=params.HwUid,
                ActorNodeName=self.name,
                FlowNodeName=params.FlowNodeName,
                PublishTicklistPeriodS=self._component.gt.PublishTicklistPeriodS,
                PublishEmptyTicklistAfterS=self._component.gt.PublishEmptyTicklistAfterS,
            )
            return Response(text=new_params.model_dump_json())
        else: # TODO: do we still need this?
            # A strange pico is identifying itself as our "a" tank
            self.log(f"Unknown pico {params.HwUid} identifying as {self.name} Pico A!")
            return Response()

    async def _handle_reed_params_post(self, request: Request) -> Response:
        # Read params as FlowReedParams
        text = await self._get_text(request)
        self.params_text = text
        try:
            params = FlowReedParams(**json.loads(text))
        except BaseException as e:
            self._report_post_error(e, "malformed tankmodule parameters!")
            self.log("Flow module params are malformed")
            return Response()
        if params.FlowNodeName != self._component.gt.FlowNodeName:
            self.log("FlowNodeName is not correct")
            return Response()
        if self._component.cac.MakeModel != MakeModel.GRIDWORKS__PICOFLOWREED:
            raise Exception(
                f"{self.name} has {self._component.cac.MakeModel} but got FlowReedParams!"
            )
        self.pico_state_log(f"{params.HwUid} PARAMS")
        # Temporary hack prior to installerapp
        # Case where a Pico gets installed and the hardware layout does not have its id yet
        if self._component.gt.HwUid is None or self._component.gt.HwUid == params.HwUid:
            if self._component.gt.HwUid is None:
                self.log(f"UPDATE LAYOUT!!: Pico HWUID {params.HwUid}")
                self.hw_uid = params.HwUid
                # TODO: update params from layout
                # TODO: send message to self so that writing to hardware layout isn't happening in IO loop
            new_params = FlowReedParams(
                HwUid=params.HwUid,
                ActorNodeName=self.name,
                FlowNodeName=params.FlowNodeName,
                PublishTicklistLength=self._component.gt.PublishTicklistLength,
                PublishAnyTicklistAfterS=self._component.gt.PublishAnyTicklistAfterS,
                DeadbandMilliseconds=params.DeadbandMilliseconds,
            )
            return Response(text=new_params.model_dump_json())
        else: # TODO: do we still need this?
            # A strange pico is identifying itself as our "a" tank
            self.log(f"Unknown pico {params.HwUid} identifying as {self.name} Pico A!")
            return Response()

    async def _handle_ticklist_hall_post(self, request: Request) -> Response:
        '''Sends a TicklistHall message to self, which will trigger _process_ticklist_hall()'''
        if self._component.cac.MakeModel != MakeModel.GRIDWORKS__PICOFLOWHALL:
            raise Exception(
                f"{self.name} has {self._component.cac.MakeModel} but got TicklistHall!"
            )
        text = await self._get_text(request)
        self.readings_text = text
        if isinstance(text, str):
            try:
                self.services.send_threadsafe(
                    Message(
                        Src=self.name,
                        Dst=self.name,
                        Payload=TicklistHall(**json.loads(text)),
                    )
                )
            except Exception as e: # noqa
                self._report_post_error(e, text)
        return Response()

    async def _handle_ticklist_reed_post(self, request: Request) -> Response:
        '''Sends a TicklistReed message to self, which will trigger _process_ticklist_reed()'''
        if self._component.cac.MakeModel != MakeModel.GRIDWORKS__PICOFLOWREED:
            raise Exception(
                f"{self.name} has {self._component.cac.MakeModel} but got TicklistReed!"
            )
        text = await self._get_text(request)
        self.readings_text = text
        if isinstance(text, str):
            try:
                self.services.send_threadsafe(
                    Message(
                        Src=self.name,
                        Dst=self.name,
                        Payload=TicklistReed(**json.loads(text)),
                    )
                )
            except Exception as e: # noqa
                self._report_post_error(e, text)
        return Response()

    def update_timestamps_for_hall(self, data: TicklistHall) -> None:
        pi_time_received_post = time.time_ns()
        pico_time_before_post = data.PicoBeforePostTimestampNanoSecond
        pico_time_delay_ns = pi_time_received_post - pico_time_before_post
        self.nano_timestamps = sorted(
            list(
                set(
                    [
                        data.FirstTickTimestampNanoSecond + x*1e3 + pico_time_delay_ns
                        for x in data.RelativeMicrosecondList
                    ]
                )
            )
        )

    def update_timestamps_for_reed(self, data: TicklistReed) -> None:
        # Consider processing more than one batch at a time (if using filtering?)
        pi_time_received_post = time.time_ns()
        pico_time_before_post = data.PicoBeforePostTimestampNanoSecond
        pico_time_delay_ns = pi_time_received_post - pico_time_before_post
        self.nano_timestamps = sorted(
            list(
                set(
                    [
                        data.FirstTickTimestampNanoSecond + x*1e6 + pico_time_delay_ns
                        for x in data.RelativeMillisecondList
                    ]
                )
            )
        )

    def publish_zero_flow(self):
        self.latest_gpm = 0
        self.latest_hz = 0
        # Set the appropriate channels to 0
        channel_names = [self.gpm_channel.Name]
        values = [0]
        if self._component.gt.SendHz:
            channel_names.append(self.hz_channel.Name)
            values.append(0)
        # Set the timestamp for the zero reading just after (100ms) the latest tick received
        zero_flow_ms = int(time.time() * 1000)
        if self.latest_tick_ns:
            zero_flow_ms = int((self.latest_tick_ns+1e8) / 1e6)
        self._send_to(
            self.primary_scada,
            SyncedReadings(
                ChannelNameList=channel_names,
                ValueList=values,
                ScadaReadTimeUnixMs=zero_flow_ms,
            )
        )
        self._send_to(
            self.pico_cycler,
            ChannelReadings(
                ChannelName=self.gpm_channel.Name,
                ValueList=[0],
                ScadaReadTimeUnixMsList=[zero_flow_ms],
            ),
        )

    def publish_first_frequency(self):
        if not self.latest_tick_ns:
            return
        # seconds_since_last_tick = (self.nano_timestamps[0]-self.latest_tick_ns)*1e9
        # if not self.slow_turner and seconds_since_last_tick > 5:
        #     self.publish_zero_flow()
        #     return
        # Frequency between last timestamp from prev list and first from current list
        first_frequency = 1/(self.nano_timestamps[0]-self.latest_tick_ns)*1e9
        # Not a slow turner: if there was less than 5s since last tick ignore this
        if not self.slow_turner and first_frequency > 1/5:
            return
        # Compute GPM and publish
        if self._component.gt.GpmFromHzMethod != GpmFromHzMethod.Constant:
            raise ValueError(f"Don't have method to handle GpmFromHzMethod {self._component.gt.GpmFromHzMethod}")
        if self.gpm_channel.TelemetryName != TelemetryName.GpmTimes100.value:
            raise ValueError(f"Expectedfor GpmTimes100 for {self.gpm_channel.Name}, got {self.gpm_channel.TelemetryName}")
        gallons_per_tick = self._component.gt.ConstantGallonsPerTick
        self.latest_gpm = first_frequency * 60 * gallons_per_tick
        self.latest_hz = first_frequency
        channel_names = [self.gpm_channel.Name]
        values = [int(self.latest_gpm * 100)]
        if self._component.gt.SendHz:
            channel_names.append(self.hz_channel.Name)
            values.append(int(self.latest_hz * 1e6))
        self._send_to(
            self.primary_scada,
            SyncedReadings(
                ChannelNameList=channel_names,
                ValueList=values,
                ScadaReadTimeUnixMs=int(self.latest_tick_ns/1e6),
            )
        )
        self._send_to(
            self.pico_cycler,
            ChannelReadings(
                ChannelName=self.gpm_channel.Name,
                ValueList=[int(self.latest_gpm*100)],
                ScadaReadTimeUnixMsList=[int(self.latest_tick_ns/1e6)],
            ),
        )

    def _process_ticklist_reed(self, data: TicklistReed) -> None:
        if data.HwUid != self.hw_uid:
            self.log(f"{self.name}: Ignoring data from pico {data.HwUid} - expect {self.hw_uid}!")
            return
        self.last_heard = time.time()

        # Report ticklist if specified in hardware layout
        if self._component.gt.SendTickLists:
            self._send_to(
                self.atn,
                TicklistReedReport(
                    TerminalAssetAlias=self.services.hardware_layout.terminal_asset_g_node_alias,
                    ChannelName=self.name,
                    ScadaReceivedUnixMs=int(time.time() * 1000),
                    Ticklist=data,
                )
            )

        # Process empty ticklist
        if len(data.RelativeMillisecondList)==0:
            if self.latest_gpm is None:
                self.publish_zero_flow()
            # Slow turner: empty ticklist does not necessarily mean no flow
            elif self.slow_turner:
                if not self.latest_tick_ns:
                    ... # TODO: come up with a fix that publishes 0 when restarting SCADA and no flow
                    # self.log("NO LATEST TICK NS")
                elif time.time()*1e9 - self.latest_tick_ns > self._component.gt.NoFlowMs*1e6:
                    self.publish_zero_flow()
            elif self.latest_gpm > self._component.gt.AsyncCaptureThresholdGpmTimes100/100:
                self.publish_zero_flow()
            return

        # Get absolute timestamps and corresponding frequency/GPM readings
        self.update_timestamps_for_reed(data)
        micro_hz_readings = self.get_micro_hz_readings()
        self.get_gpm_readings(micro_hz_readings)

    def _process_ticklist_hall(self, data: TicklistHall) -> None:
        if data.HwUid != self.hw_uid:
            self.log(f"Ignoring data from pico {data.HwUid} - expect {self.hw_uid}!")
            return
        self.last_heard = time.time()

        # Report ticklist if specified in hardware layout
        if self._component.gt.SendTickLists:
            self._send_to(
                self.atn,
                TicklistHallReport(
                    TerminalAssetAlias=self.services.hardware_layout.terminal_asset_g_node_alias,
                    ChannelName=self._component.gt.FlowNodeName,
                    ScadaReceivedUnixMs=int(time.time() * 1000),
                    Ticklist=data,
                ),
            )

        # Process empty ticklist
        if len(data.RelativeMicrosecondList)==0:
            if self.latest_gpm is None:
                self.publish_zero_flow()
            elif self.latest_gpm > self._component.gt.AsyncCaptureThresholdGpmTimes100/100:
                self.publish_zero_flow()
            return

        # Get absolute timestamps and corresponding frequency/GPM readings
        self.update_timestamps_for_hall(data)
        micro_hz_readings = self.get_micro_hz_readings()
        self.get_gpm_readings(micro_hz_readings)

    def get_gpm_readings(self, micro_hz_readings: ChannelReadings):
        if self._component.gt.GpmFromHzMethod != GpmFromHzMethod.Constant:
            raise ValueError(f"Don't have method to handle GpmFromHzMethod {self._component.gt.GpmFromHzMethod}")
        if self.gpm_channel.TelemetryName != TelemetryName.GpmTimes100.value:
            raise ValueError(f"Expectedfor GpmTimes100 for {self.gpm_channel.Name}, got {self.gpm_channel.TelemetryName}")
        if not micro_hz_readings.ValueList:
            self.log("Empty micro hz list in get_gpm_readings")
            return
        gallons_per_tick = self._component.gt.ConstantGallonsPerTick
        hz_list = [x / 1e6 for x in micro_hz_readings.ValueList]
        gpms = [x * 60 * gallons_per_tick for x in hz_list]
        self.latest_gpm = gpms[-1]
        gpm_readings = ChannelReadings(
            ChannelName=self.gpm_channel.Name,
            ValueList=[int(x*100) for x in gpms],
            ScadaReadTimeUnixMsList=micro_hz_readings.ScadaReadTimeUnixMsList,
        )
        self._send_to(self.primary_scada, gpm_readings)
        self._send_to(self.pico_cycler, gpm_readings)
        if self._component.gt.SendHz:
            self._send_to(self.primary_scada, micro_hz_readings)

    def get_micro_hz_readings(self) -> ChannelReadings:
        if len(self.nano_timestamps)==0:
            raise ValueError("Should not call get_hz_readings with an empty ticklist!")

        # Single tick
        if len(self.nano_timestamps)==1:
            if self.latest_tick_ns is not None:
                frequency_hz = 1e9 / (self.nano_timestamps[0] - self.latest_tick_ns)
            else:
                frequency_hz = 0
            if self.slow_turner:
                micro_hz_readings = ChannelReadings(
                    ChannelName=self.hz_channel.Name,
                    ValueList=[int(frequency_hz * 1e6)],
                    ScadaReadTimeUnixMsList=[int(self.nano_timestamps[0]/1e6)]
                )
            else:
                micro_hz_readings = ChannelReadings(
                    ChannelName=self.hz_channel.Name,
                    ValueList=[int(frequency_hz * 1e6), 0],
                    ScadaReadTimeUnixMsList=[int(self.nano_timestamps[0]/1e6), int(self.nano_timestamps[0]/1e6)+100]
                )
            self.latest_tick_ns = self.nano_timestamps[-1]
            self.latest_hz = frequency_hz if self.slow_turner else 0
            return micro_hz_readings

        # Post flow between the latest tick and the first tick
        # if self.latest_tick_ns:
        #     self.publish_first_frequency()

        # Sort timestamps and compute frequencies
        timestamps = sorted(self.nano_timestamps)
        frequencies = [1/(t2-t1)*1e9 for t1,t2 in zip(timestamps[:-1], timestamps[1:])]
        timestamps = timestamps[:-1]

        if not self.slow_turner:
            # Remove outliers
            min_hz, max_hz = 0, 500
            tf_pairs = [(t,f) for t,f in zip(timestamps, frequencies) if f<=max_hz and f>=min_hz]
            timestamps = [x[0] for x in tf_pairs]
            frequencies = [x[1] for x in tf_pairs]
            if not timestamps:
                return ChannelReadings(
                    ChannelName=self.hz_channel.Name,
                    ValueList=[],
                    ScadaReadTimeUnixMsList=[],
                )

            # Add 0 flow when there is more than no_flow_ms between two points
            new_timestamps, new_frequencies = [], []
            for i in range(len(timestamps) - 1):
                new_timestamps.append(timestamps[i]) 
                new_frequencies.append(frequencies[i])  
                if timestamps[i+1] - timestamps[i] > self._component.gt.NoFlowMs*1e6:
                    step_20ms = 0.02*1e9
                    while new_timestamps[-1] + step_20ms < timestamps[i+1]:
                        new_timestamps.append(new_timestamps[-1] + step_20ms)
                        new_frequencies.append(0.001)
            new_timestamps.append(timestamps[-1])
            new_frequencies.append(frequencies[-1])
            sorted_times_values = sorted(zip(new_timestamps, new_frequencies))
            timestamps, frequencies = zip(*sorted_times_values)

        # First reading
        first_reading = False
        if self.latest_hz is None:
            first_reading = True
            self.latest_hz = frequencies[0]

        # No processing for slow turners
        if self.slow_turner:
            sampled_timestamps = timestamps
            smoothed_frequencies = frequencies
            self.latest_hz = smoothed_frequencies[-1]
            self.latest_tick_ns = sorted(self.nano_timestamps)[-1]
            return ChannelReadings(
                ChannelName=self.hz_channel.Name,
                ValueList=[int(x*1e6) for x in smoothed_frequencies],
                ScadaReadTimeUnixMsList=[int(x/1e6) for x in sampled_timestamps],
            )

        # [Processing] Exponential weighted average
        elif self._component.gt.HzCalcMethod == HzCalcMethod.BasicExpWeightedAvg:
            alpha = self._component.gt.ExpAlpha
            smoothed_frequencies = [self.latest_hz]*len(frequencies)
            for t in range(len(frequencies)-1):
                smoothed_frequencies[t+1] = (1-alpha)*smoothed_frequencies[t] + alpha*frequencies[t+1]
            sampled_timestamps = timestamps

        # [Processing] Butterworth filter
        elif self._component.gt.HzCalcMethod == HzCalcMethod.BasicButterWorth:
            if len(frequencies) > 20:
                # Add the last recorded frequency before the filtering (avoids overfitting the first point)
                timestamps = [timestamps[0]-0.01*1e9] + list(timestamps)
                frequencies = [self.latest_hz] + list(frequencies)
                # Re-sample time at sampling frequency f_s
                f_s = 5 * max(frequencies)
                sampled_timestamps = np.linspace(min(timestamps), max(timestamps), int((max(timestamps)-min(timestamps))/1e9 * f_s))
                # Re-sample frequency accordingly using a linear interpolaton
                sampled_frequencies = np.interp(sampled_timestamps, timestamps, frequencies)
                # Butterworth low-pass filter
                b, a = butter_lowpass(N=5, Wn=self._component.gt.CutoffFrequency, fs=f_s)
                smoothed_frequencies = filtering(b, a, sampled_frequencies)
                # Remove points resulting from adding the first recorded frequency
                smoothed_frequencies = [
                    smoothed_frequencies[i]
                    for i in range(len(smoothed_frequencies))
                    if sampled_timestamps[i]>=timestamps[1]
                ]
                sampled_timestamps = [x for x in sampled_timestamps if x>=timestamps[1]]
            else:
                self.log(f"Warning: ticklist was too short ({len(frequencies)} instead of minimum 20) for butterworth.")
                sampled_timestamps = timestamps
                smoothed_frequencies = frequencies

        # Sanity checks after processing
        if not sampled_timestamps or len(sampled_timestamps) != len(smoothed_frequencies) :
            if not sampled_timestamps:
                glitch_summary = "Filtering resulted in a list of length 0"
            else:
                glitch_summary = "Sampled Timestamps and Smoothed Frequencies not the same length!"
            self._send_to(
                self.atn,
                Glitch(
                    FromGNodeAlias=self.layout.scada_g_node_alias,
                    Node=self.node.name,
                    Type=LogLevel.Warning,
                    Summary=glitch_summary,
                    Details=f"get_micro_hz_readings, nano_timestamps were {self.nano_timestamps}"
                )
            )
            if not sampled_timestamps:
                return ChannelReadings(
                    ChannelName=self.hz_channel.Name,
                    ValueList=[],
                    ScadaReadTimeUnixMsList=[],
                )
            else:
                raise Exception("Sampled Timestamps and Smoothed Frequencies not the same length!")
        
        # Record Hz on change
        threshold_gpm = self._component.gt.AsyncCaptureThresholdGpmTimes100 / 100
        gallons_per_tick = self._component.gt.ConstantGallonsPerTick
        threshold_hz = threshold_gpm / 60 / gallons_per_tick
        if first_reading:
            self.latest_hz = smoothed_frequencies[0]
        micro_hz_list = [int(self.latest_hz * 1e6)]
        unix_ms_times = [int(sampled_timestamps[0] / 1e6)]
        for i in range(1, len(smoothed_frequencies)):
            if abs(smoothed_frequencies[i] - micro_hz_list[-1]/1e6) > threshold_hz:
                micro_hz_list.append(int(smoothed_frequencies[i] * 1e6))
                unix_ms_times.append(int(sampled_timestamps[i] / 1e6))
        self.latest_hz = micro_hz_list[-1]/1e6
        self.latest_tick_ns = sorted(self.nano_timestamps)[-1]
        micro_hz_list = [x if x>0 else 0 for x in micro_hz_list]
        
        return ChannelReadings(
            ChannelName=self.hz_channel.Name,
            ValueList=micro_hz_list,
            ScadaReadTimeUnixMsList=unix_ms_times,
        )
    
    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case TicklistReed():
                self._process_ticklist_reed(message.Payload)
            case TicklistHall():
                self._process_ticklist_hall(message.Payload)
        return Ok(True)

    def start(self) -> None:
        self.services.add_task(
            asyncio.create_task(self.main(), name="ApiFlowModule keepalive")
        )

    def stop(self) -> None:
        """
        IOLoop will take care of shutting down webserver interaction.
        Here we stop periodic reporting task.
        """
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

import asyncio
import json
import time
from functools import cached_property
from typing import Optional, Sequence

from actors.glitch_limit import REPEAT_GLITCH_S, GlitchLimit
from actors.pico_actor_base import PicoActorBase
from actors.pico_identity import PicoIdentity
from actors.pico_liveness import PicoLiveness
from actors.pico_post_refusal import RefusedPosts, refused_post, unknown_pico, unreadable_post
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproactor import MonitoredName
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import PicoBtuMeterComponent, SimPicoBtuMeterComponent
from gwsproto.enums import DeviceType, PicoBoardVariant, SimDeviceType
from gwsproto.names.core.node_names import ScadaWeb
from gwsproto.named_types import (
    AsyncBtuParams, ChannelFlatlined, Glitch,
    MultichannelSnapshot, PicoMissing, SyncedReadings
)
from plant import PlantReadings, SensorSource
from result import Ok, Result
from scada_app_interface import ScadaAppInterface

# The pico drops a thermistor at either rail before it posts; one near a
# rail gets past that guard as a temperature no hydronic pipe reaches.
IMPLAUSIBLE_BELOW_C = -40.0
IMPLAUSIBLE_ABOVE_C = 130.0


class ApiBtuMeter(PicoActorBase):
    """Reads a pico BTU meter's posts over HTTP. A component of the sim
    word has no pico: the plant shows its channels, already in each
    channel's encoding, and each flux that carries one is taken as a post,
    so a plant that stops showing them is a pico that stopped posting."""

    _stop_requested: bool
    _component: PicoBtuMeterComponent | SimPicoBtuMeterComponent

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)

        comp = self.node.component
        if comp is None:
            raise Exception(f" {self.node.actor_class} {self.name} needs a component!")

        if not isinstance(comp, (PicoBtuMeterComponent, SimPicoBtuMeterComponent)):
            display_name = getattr(
                comp.gt, "DisplayName", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> for node {self.name} has type {type(comp)}. "
                f"Expected PicoBtuMeterComponent or SimPicoBtuMeterComponent.\n"
            )
        self._component = comp
        # Btu meters carry no specialized device-type record; identity is on the gt.
        self.device_type = self._component.gt.DeviceType
        if self.device_type not in [DeviceType.Gw101, SimDeviceType.SimSensor]:
            raise ValueError(
                f"Expect Gw101 (BtuMeter) or SimSensor.. not {self.device_type}"
            )
        self._stop_requested: bool = False
        # Built but idle: a disabled node keeps its routes and its place in
        # the cycler's roster, and neither reads, reports nor alerts.
        self.disabled: bool = self.layout.node_disabled(self.name)

        self._services.add_web_route(
            server_name=ScadaWeb.DEFAULT_SERVER_NAME,
            method="POST",
            path="/" + self.async_btu_params_path,
            handler=self._handle_async_btu_params_post,
        )
        self._services.add_web_route(
            server_name=ScadaWeb.DEFAULT_SERVER_NAME,
            method="POST",
            path="/" + self.multichannel_snapshot_path,
            handler=self._handle_multichannel_snapshot_post,
        )
        self.pico_uid = self._component.gt.HwUid
        self.refused_posts = RefusedPosts(self)
        # One Warning a day per channel for a thermistor that reads
        # impossibly or stops arriving while its siblings post
        self.glitch_limit = GlitchLimit(REPEAT_GLITCH_S)
        self.pico_identity: Optional[PicoIdentity] = None
        if isinstance(self._component, PicoBtuMeterComponent):
            self.pico_identity = PicoIdentity(
                # the BTU component twin holds its enums as their values
                board_variant=PicoBoardVariant(self._component.gt.PicoBoardVariant),
                micropython_version=self._component.gt.MicropythonVersion,
            )
        # Find channels by matching AboutNodeName to component's node names
        self.flow_channel = self.layout.channel(self._component.gt.FlowChannelName)
        self.liveness = PicoLiveness(
            expected_post_s=self.layout.capture_tuning_by_channel[
                self.flow_channel.Name
            ].CapturePeriodS
        )
        self.hot_temp_channel = self.layout.channel(self._component.gt.HotChannelName)
        self.cold_temp_channel = self.layout.channel(self._component.gt.ColdChannelName)
        # CT channel is optional
        self.ct_channel = None
        if self._component.gt.CtChannelName:
            self.ct_channel = self.layout.channel(self._component.gt.CtChannelName)
        # The channels this actor reads, reports and alerts on: the
        # component's, less the disabled ones.
        self.enabled_channel_names: set[str] = set(
            self.layout.enabled_channel_names(
                ch.Name
                for ch in (self.flow_channel, self.hot_temp_channel, self.cold_temp_channel, self.ct_channel)
                if ch is not None
            )
        )
        self.channel_liveness: dict[str, PicoLiveness] = {
            ch.Name: PicoLiveness(
                expected_post_s=self.layout.capture_tuning_by_channel[ch.Name].CapturePeriodS
            )
            for ch in self.flatlined_channels()
        }
        self.feeds_derived = self.layout.feeds_derived(self.enabled_channel_names)

        if isinstance(self._component, SimPicoBtuMeterComponent):
            self.my_device(SensorSource).sense(
                [
                    ch.Name
                    for ch in self.layout.data_channels.values()
                    if ch.CapturedByNodeName == self.name
                ],
                self.take_from_plant,
            )

    @cached_property
    def async_btu_params_path(self) -> str:
        return f"{self.name}/async-btu-params"

    @cached_property
    def multichannel_snapshot_path(self) -> str:
        return f"{self.name}/multichannel-snapshot"

    async def _get_text(self, request: Request) -> Optional[str]:
        try:
            return await request.text()
        except Exception as e:
            self.refused_posts.report(unreadable_post(self.name, e))
        return None

    def is_valid_pico_uid(self, params: AsyncBtuParams) -> bool:
        if params.HwUid == self._component.gt.HwUid:
            return True
        return False

    def need_to_update_layout(self, params: AsyncBtuParams) -> bool:
        if self._component.gt.HwUid:
            return False
        else:
            return True

    async def _handle_async_btu_params_post(self, request: Request) -> Response:
        #print("GOT BTU PARAMS")
        text = await self._get_text(request)
        self.params_text = text
        #self.log(f"Params received: {text}")
        if text is None:
            return Response()
        try:
            params = AsyncBtuParams(**json.loads(text))
        except BaseException as e:
            self.refused_posts.report(refused_post(self.name, text, e, AsyncBtuParams))
            r = Response()
            self.log(f"malformed BtuMeter parameters: {e}")
            return r
        if params.ActorNodeName != self.name:
            r = Response()
            self.log(
                f"ActorNodeName {params.ActorNodeName} not {self.name}! returning {r}"
            )
            return r

        # Check if this is our pico (or if we don't have one yet)
        if self.is_valid_pico_uid(params):
            self.services.send_threadsafe(
                Message(Src=self.name, Dst=self.name, Payload=params.model_copy())
            )
            # Update the pico's configuration to match our layout
            params.FlowChannelName = self._component.gt.FlowChannelName
            params.SendHz = self._component.gt.SendHz
            params.ReadCtVoltage = self._component.gt.ReadCtVoltage
            params.HotChannelName = self._component.gt.HotChannelName
            params.ColdChannelName = self._component.gt.ColdChannelName
            params.CtChannelName = self._component.gt.CtChannelName
            params.ThermistorBeta = self._component.gt.ThermistorBeta

            params.AsyncCaptureDeltaCelsiusX100 = self._component.gt.AsyncCaptureDeltaCelsiusX100
            params.AsyncCaptureDeltaGpmX100 = self._component.gt.AsyncCaptureDeltaGpmX100
            params.AsyncCaptureDeltaCtVoltsX100 = self._component.gt.AsyncCaptureDeltaCtVoltsX100
            # Set timing parameters

            period = self.layout.capture_tuning_by_channel[
                self.flow_channel.Name
            ].CapturePeriodS


            # Calculate seconds until next minute boundary
            seconds_to_next_top = period - (time.time() % period)
            self.log(
                f"btu report period of {period}s. seconds_to_next_top is {round(seconds_to_next_top, 1)}"
            )

            # Subtract 7.5 seconds to give the pico time to prepare
            # If this would be negative, wrap around to the previous cycle
            offset = seconds_to_next_top
            # if offset < 0:
            #     offset += period

            offset = round(offset, 1)
            params.CapturePeriodS = period
            params.CaptureOffsetS = offset

            # If this is a new pico, log the HwUid for layout update
            if self.need_to_update_layout(params):
                if self.device_type == DeviceType.Gw101:
                    self.pico_uid = params.HwUid
                    self.log(
                        f"UPDATE LAYOUT!!: set HwUid = '{params.HwUid}' on "
                        f"{self.name}'s component in the layout"
                    )
            txt=params.model_dump_json()
            # self.log(f"Valid pico id. returning {txt}")
            return Response(text=txt)
        else:
            self.log(f"unknown pico {params.HwUid} identifying as {self.name}")
            self.refused_posts.report(
                unknown_pico(self.name, params.HwUid, self._component.gt.HwUid)
            )
            return Response()

    def check_pico_identity(self, params: AsyncBtuParams) -> None:
        """Warns once per difference between the post's board and MicroPython
        version and the layout's. The layout value is what the house was
        provisioned with; the scada does not write it."""
        if self.pico_identity is None:
            return
        for d in self.pico_identity.differences(
            params.PicoBoardVariant, params.MicropythonVersion
        ):
            self.send_warning(
                summary=d.summary(self.name), details=d.details(params.HwUid)
            )

    async def _handle_multichannel_snapshot_post(self, request: Request) -> Response:
        text = await self._get_text(request)
        if text is None:
            return Response(text="failed", status=100)
        try:
            data = MultichannelSnapshot(**json.loads(text))
        except Exception as e:
            self.log(f"Did not interpret data as MultichannelSnapshot: {e}")
            self.refused_posts.report(refused_post(self.name, text, e, MultichannelSnapshot))
            return Response(text="failed", status=100)

        self.readings_text = text
        try:
            self.services.send_threadsafe(
                Message(
                    Src=self.name,
                    Dst=self.name,
                    Payload=data,
                )
            )
        except Exception as e:  # noqa
            self.refused_posts.report(refused_post(self.name, text, e, MultichannelSnapshot))
        return Response()

    def _process_multichannel_snapshot(self, data: MultichannelSnapshot) -> None:
        if data.HwUid == self.pico_uid:
            now = time.time()
            self.liveness.heard(now)
            for channel_name in data.ChannelNameList:
                if channel_name in self.channel_liveness:
                    self.channel_liveness[channel_name].heard(now)
        else:
            self.log(
                f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!"
            )
            return
        # The pico posts temperatures as CelsiusTimes100; each goes out in its
        # channel's declared encoding
        channel_names = []
        converted_values = []
        for channel_name, measurement, unit in zip(
            data.ChannelNameList, data.MeasurementList, data.UnitList
        ):
            if channel_name not in self.enabled_channel_names:
                continue
            if unit == "CelsiusTimes100":
                celsius = measurement / 100
                if celsius < IMPLAUSIBLE_BELOW_C or celsius > IMPLAUSIBLE_ABOVE_C:
                    if self.glitch_limit.due(f"open-thermistor:{channel_name}"):
                        self.send_warning(
                            "open-thermistor",
                            f"{channel_name} reads {celsius} C, a thermistor near a pico rail",
                        )
                    continue
                converted_values.append(
                    self.layout.channel_registry.temperature_from_c(
                        channel_name, celsius
                    ).raw
                )
            else:
                # Keep other measurements as-is
                converted_values.append(measurement)
            channel_names.append(channel_name)
        self.report_readings(channel_names, converted_values, int(time.time() * 1000))

    def take_from_plant(self, readings: PlantReadings) -> None:
        if self.disabled:
            return
        now = time.time()
        self.liveness.heard(now)
        enabled = [
            i for i, name in enumerate(readings.channel_names) if name in self.enabled_channel_names
        ]
        for i in enabled:
            self.channel_liveness[readings.channel_names[i]].heard(now)
        self.report_readings(
            [readings.channel_names[i] for i in enabled],
            [readings.values[i] for i in enabled],
            readings.read_time_ms,
        )

    def report_readings(
        self, channel_names: list[str], values: list[int], read_time_ms: int
    ) -> None:
        if not channel_names:
            return
        msg = SyncedReadings(
            ChannelNameList=channel_names,  # TODO OPS-35 disambiguate between AboutNodeNames and ChannelNames
            ValueList=values,
            ScadaReadTimeUnixMs=read_time_ms,
        )
        self._send_to(self.pico_cycler, msg)
        self._send_to(self.primary_scada, msg)
        if self.feeds_derived:
            self._send_to(self.derived_generator, msg)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case MultichannelSnapshot():
                self._process_multichannel_snapshot(message.Payload)
            case Glitch():
                self._send_to(self.ltn, message.Payload)
            case AsyncBtuParams():
                self.check_pico_identity(message.Payload)
        return Ok(True)

    def start(self) -> None:
        """IOLoop will take care of start."""
        self.services.add_task(
            asyncio.create_task(self.main(), name="ApiBtuMeter keepalive")
        )

    def stop(self) -> None:
        """IOLoop will take care of stop."""
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

    def flatline_seconds(self) -> float:
        return self.liveness.flatline_seconds

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.flatline_seconds() * 2.1)]

    def missing(self) -> bool:
        return self.liveness.missing(time.time())

    def flatlined_channels(self) -> list:
        channels = [self.flow_channel, self.hot_temp_channel, self.cold_temp_channel]
        if self.ct_channel:
            channels.append(self.ct_channel)
        return [ch for ch in channels if ch.Name in self.enabled_channel_names]

    def report_missing(self) -> None:
        if not self.pico_uid:
            return
        self._send_to(
            self.pico_cycler,
            PicoMissing(ActorName=self.name, PicoHwUid=self.pico_uid),
        )
        for channel in self.flatlined_channels():
            self._send_to(
                self.primary_scada,
                ChannelFlatlined(FromName=self.name, Channel=channel),
            )

    def check_liveness(self) -> None:
        """The whole pico by its posts, then each channel by the posts that
        carry it. A quiet channel on a posting pico is flatlined at the
        scada and is no PicoMissing; a missing pico is not also reported
        channel by channel."""
        if self.disabled:
            return
        now = time.time()
        if self.liveness.report_due(now):
            self.report_missing()
        if self.liveness.missing(now):
            return
        for channel_name, liveness in self.channel_liveness.items():
            if liveness.report_due(now):
                self._send_to(
                    self.primary_scada,
                    ChannelFlatlined(
                        FromName=self.name,
                        Channel=self.layout.data_channels[channel_name],
                    ),
                )
                if self.glitch_limit.due(f"quiet-channel:{channel_name}"):
                    self.send_warning(
                        "quiet-channel",
                        f"{channel_name} stopped arriving while pico {self.pico_uid} posts its other channels",
                    )

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.check_liveness()
            await asyncio.sleep(10)

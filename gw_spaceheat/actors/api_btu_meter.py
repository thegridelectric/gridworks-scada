import asyncio
import json
import time
from functools import cached_property
from typing import Optional, Sequence

from actors.pico_actor_base import PicoActorBase
from actors.pico_identity import PicoIdentity
from actors.pico_liveness import PicoLiveness
from actors.sim_pico_source import SIM_PICO_TICK_S, SimPicoSource
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproactor import MonitoredName, Problems
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import PicoBtuMeterComponent, SimPicoBtuMeterComponent
from gwsproto.enums import DeviceType, PicoBoardVariant, RelayClosedOrOpen, SimDeviceType
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames
from gwsproto.names.core.node_names import ScadaWeb
from gwsproto.named_types import (
    AsyncBtuParams, ChannelFlatlined, 
    MultichannelSnapshot, PicoMissing, SyncedReadings
)
from result import Ok, Result
from scada_app_interface import ScadaAppInterface

# A loop with standing flow and no lift: 4 gpm, both pipes at 50 C, no CT
# voltage. Fixed until the plant drives loop flow and temperatures.
SIM_LOOP_GPM_X100 = 400
SIM_LOOP_CELSIUS_X100 = 5000
SIM_CT_VOLTS_X100 = 0


def snapshot_without(
    reading: MultichannelSnapshot, channel_names: set[str]
) -> MultichannelSnapshot:
    """The snapshot with the named channels dropped from its lists."""
    kept = [
        i for i, name in enumerate(reading.ChannelNameList) if name not in channel_names
    ]
    return MultichannelSnapshot(
        HwUid=reading.HwUid,
        ChannelNameList=[reading.ChannelNameList[i] for i in kept],
        MeasurementList=[reading.MeasurementList[i] for i in kept],
        UnitList=[reading.UnitList[i] for i in kept],
    )


class ApiBtuMeter(PicoActorBase):
    """Reads a pico BTU meter over HTTP. When the component is the sim word
    the actor runs its own SimPicoSource, posting snapshots to itself on the
    path the web handler uses for a real pico's post."""

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

        if self._component.gt.Enabled:
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
        self.channel_liveness: dict[str, PicoLiveness] = {
            ch.Name: PicoLiveness(
                expected_post_s=self.layout.capture_tuning_by_channel[ch.Name].CapturePeriodS
            )
            for ch in self.flatlined_channels()
        }
        self.feeds_derived = self.layout.feeds_derived(
            ch.Name
            for ch in (self.flow_channel, self.hot_temp_channel, self.cold_temp_channel, self.ct_channel)
            if ch is not None
        )

        self.sim_pico: Optional[SimPicoSource[MultichannelSnapshot]] = None
        if isinstance(self._component, SimPicoBtuMeterComponent):
            assert self.pico_uid
            channel_names = [self.flow_channel.Name, self.hot_temp_channel.Name, self.cold_temp_channel.Name]
            measurements = [SIM_LOOP_GPM_X100, SIM_LOOP_CELSIUS_X100, SIM_LOOP_CELSIUS_X100]
            units = ["GpmTimes100", "CelsiusTimes100", "CelsiusTimes100"]
            if self.ct_channel is not None:
                channel_names.append(self.ct_channel.Name)
                measurements.append(SIM_CT_VOLTS_X100)
                units.append("VoltsTimes100")
            self.sim_pico = SimPicoSource(
                reading=MultichannelSnapshot(
                    HwUid=self.pico_uid,
                    ChannelNameList=channel_names,
                    MeasurementList=measurements,
                    UnitList=units,
                ),
                without=snapshot_without,
                capture_period_s=self.liveness.expected_post_s,
                life_s=self._component.gt.SimLifeS,
                reboot_s=self._component.gt.SimRebootS,
                booted_at=time.time(),
            )
        self.sim_relay_seen: Optional[tuple[str, int]] = None

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
            self.services.send_threadsafe(
                Message(
                    Payload=Problems(errors=[e]).problem_event(
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
                        "Pico POST processing error for "
                        f"<{self._name}>: {type(exception)} <{exception}>"
                    ),
                )
            )
        )

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
        try:
            params = AsyncBtuParams(**json.loads(text))
        except BaseException as e:
            self._report_post_error(e, "malformed BtuMeter parameters!")
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
            # A strange pico is identifying itself as our "a" tank
            self.log(f"unknown pico {params.HwUid} identifying as {self.name}")
            # TODO: send problem report?
            return Response()

    def check_pico_identity(self, params: AsyncBtuParams) -> None:
        """Warns once per difference between the post's board and MicroPython
        version and the layout's. The layout value is what the house was
        provisioned with; the scada does not write it. The first post that
        matches sends a debug glitch."""
        if self.pico_identity is None:
            return
        for d in self.pico_identity.differences(
            params.PicoBoardVariant, params.MicropythonVersion
        ):
            self.send_warning(
                summary=d.summary(self.name), details=d.details(params.HwUid)
            )
        if self.pico_identity.first_match(
            params.PicoBoardVariant, params.MicropythonVersion
        ):
            self.send_debug(
                summary="pico-identity-matches",
                details=(
                    f"pico {params.HwUid} posted {params.PicoBoardVariant.value}, "
                    f"MicroPython {params.MicropythonVersion}"
                ),
            )

    async def _handle_multichannel_snapshot_post(self, request: Request) -> Response:
        text = await self._get_text(request)
        #self.log("GOT BTU DATA")
        try:
            data = MultichannelSnapshot(**json.loads(text))
        except Exception as e:
            self.log(f"Did not interpret data as MultichannelSnapshot: {e}")
            return Response(text="failed", status=100)

        self.readings_text = text
        if isinstance(text, str):
            try:
                self.services.send_threadsafe(
                    Message(
                        Src=self.name,
                        Dst=self.name,
                        Payload=MultichannelSnapshot(**json.loads(text)),
                    )
                )
            except Exception as e:  # noqa
                self._report_post_error(e, text)
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
        converted_values = []
        for channel_name, measurement, unit in zip(
            data.ChannelNameList, data.MeasurementList, data.UnitList
        ):
            if unit == "CelsiusTimes100":
                converted_values.append(
                    self.layout.channel_registry.temperature_from_c(
                        channel_name, measurement / 100
                    ).raw
                )
            else:
                # Keep other measurements as-is
                converted_values.append(measurement)

        # Create and send the synced readings message
        msg = SyncedReadings(
            ChannelNameList=data.ChannelNameList,  # TODO OPS-35 disambiguate between AboutNodeNames and ChannelNames
            ValueList=converted_values,
            ScadaReadTimeUnixMs=int(time.time() * 1000),
        )
        self._send_to(self.pico_cycler, msg)
        self._send_to(self.primary_scada, msg)
        if self.feeds_derived:
            self._send_to(self.derived_generator, msg)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case MultichannelSnapshot():
                self._process_multichannel_snapshot(message.Payload)
            case AsyncBtuParams():
                self.check_pico_identity(message.Payload)
        return Ok(True)

    def start(self) -> None:
        """IOLoop will take care of start."""
        self.services.add_task(
            asyncio.create_task(self.main(), name="ApiBtuMeter keepalive")
        )
        if self.sim_pico is not None:
            self.services.add_task(
                asyncio.create_task(self.sim_pico_main(), name="ApiBtuMeter sim pico")
            )

    def feed_sim_relay_state(self, now: float) -> None:
        """Hand the source each new vdc relay state from the scada's latest
        machine states."""
        assert self.sim_pico is not None
        sms = self.data.latest_machine_state.get(HydronicSpaceheatNodeNames.vdc_relay)
        if sms is None:
            return
        seen = (sms.State, sms.UnixMs)
        if seen == self.sim_relay_seen:
            return
        self.sim_relay_seen = seen
        self.sim_pico.relay_state(RelayClosedOrOpen(sms.State), now)

    async def sim_pico_main(self) -> None:
        assert self.sim_pico is not None
        while not self._stop_requested:
            now = time.time()
            self.feed_sim_relay_state(now)
            reading = self.sim_pico.tick(now)
            if reading is not None:
                self.services.send_threadsafe(
                    Message(Src=self.name, Dst=self.name, Payload=reading)
                )
            await asyncio.sleep(SIM_PICO_TICK_S)

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
        return channels

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
        if not self._component.gt.Enabled:
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

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            self.check_liveness()
            await asyncio.sleep(10)

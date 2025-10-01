import asyncio
import json
import time
from functools import cached_property
from typing import Optional, Sequence

from actors.pico_actor_base import PicoActorBase
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproactor import MonitoredName, Problems
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.components import PicoBtuMeterComponent
from gwproto.enums import MakeModel
from gwproto.named_types import SyncedReadings
from gwproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from gwsproto.named_types import MultichannelSnapshot,  AsyncBtuParams, ChannelFlatlined, PicoMissing
from result import Ok, Result
from scada_app_interface import ScadaAppInterface
FLATLINE_REPORT_S = 60


class ApiBtuMeter(PicoActorBase):
    _stop_requested: bool
    _component: PicoBtuMeterComponent

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
    ):
        super().__init__(name, services)

        comp = self._node.component
        if comp is None:
            raise Exception(f" {self.node.actor_class} {self.name} needs a component!")

        if not isinstance(comp, PicoBtuMeterComponent):
            display_name = getattr(
                comp.gt, "DisplayName", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> for node {self.name} has type {type(comp)}. "
                f"Expected PicoBtuMeterComponent.\n"
            )
        self._component = comp
        self.device_type = self._component.cac
        if self.device_type.MakeModel not in [MakeModel.GRIDWORKS__GW101]:
            raise ValueError(
                f"Expect Gw101 (BtuMeter).. not {self.device_type.MakeModel}"
            )
        self._stop_requested: bool = False

        if self._component.gt.Enabled:
            self._services.add_web_route(
                server_name=DEFAULT_WEB_SERVER_NAME,
                method="POST",
                path="/" + self.async_btu_params_path,
                handler=self._handle_async_btu_params_post,
            )
            self._services.add_web_route(
                server_name=DEFAULT_WEB_SERVER_NAME,
                method="POST",
                path="/" + self.multichannel_snapshot_path,
                handler=self._handle_multichannel_snapshot_post,
            )
        self.pico_uid = self._component.gt.HwUid
        self.last_heard = time.time()  # used for monitoring flatlined pico
        self.last_error_report = time.time()
        # Find channels by matching AboutNodeName to component's node names
        self.flow_channel = self.layout.channel(self._component.gt.FlowChannelName)
        self.hot_temp_channel = self.layout.channel(self._component.gt.HotChannelName)
        self.cold_temp_channel = self.layout.channel(self._component.gt.ColdChannelName)
        # CT channel is optional
        self.ct_channel = None
        if self._component.gt.CtChannelName:
            self.ct_channel = self.layout.channel(self._component.gt.CtChannelName)

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

            # Find the config for the flow channel. Must exist via layout axioms
            flow_config = next(
                (
                    cfg
                    for cfg in self._component.gt.ConfigList
                    if cfg.ChannelName == self.flow_channel.Name
                ),
            )

            period = flow_config.CapturePeriodS


            # Calculate seconds until next minute boundary
            seconds_to_next_top = period - (time.time() % period)
            self.log(
                f"btu report period of {period}s. seconds_to_next_top is {seconds_to_next_top}"
            )

            # Subtract 7.5 seconds to give the pico time to prepare
            # If this would be negative, wrap around to the previous cycle
            offset = seconds_to_next_top
            # if offset < 0:
            #     offset += period

            offset = round(offset, 1)
            params.CapturePeriodS = period
            params.CaptureOffsetS = offset
            print(f"SENDING OFFSET OF {offset}")

            # If this is a new pico, log the HwUid for layout update
            if self.need_to_update_layout(params):
                if self.device_type.MakeModel == MakeModel.GRIDWORKS__GW101:
                    self.pico_uid = params.HwUid
                    self.log(
                        f"UPDATE LAYOUT!!: In layout_gen, go to ### {self.name} "
                        f"and add HwUid = '{params.HwUid}'"
                    )
            txt=params.model_dump_json()
            self.log(f"Valid pico id. returning {txt}")
            return Response(text=txt)
        else:
            # A strange pico is identifying itself as our "a" tank
            self.log(f"unknown pico {params.HwUid} identifying as {self.name}")
            # TODO: send problem report?
            return Response()

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
        self.log(f"got {data}")
        if data.HwUid == self.pico_uid:
            self.last_heard = time.time()
        else:
            self.log(
                f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!"
            )
            return
        # Convert temperature units where needed
        converted_values = []
        for i, (measurement, unit) in enumerate(
            zip(data.MeasurementList, data.UnitList)
        ):
            if unit == "CelsiusTimes100":
                # Convert CelsiusTimes100 to WaterTempCTimes1000
                # (multiply by 10 to go from x100 to x1000)
                converted_values.append(measurement * 10)
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

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case MultichannelSnapshot():
                self._process_multichannel_snapshot(message.Payload)
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
        cfg = next(
            cfg
            for cfg in self._component.gt.ConfigList
            if cfg.ChannelName == f"{self.flow_channel.Name}"
        )
        return cfg.CapturePeriodS * 2.5

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.flatline_seconds() * 2.1)]

    def missing(self) -> bool:
        return time.time() - self.last_heard > self.flatline_seconds()

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if (
                time.time() - self.last_heard > self.flatline_seconds()
                and time.time() - self.last_error_report > FLATLINE_REPORT_S
            ):
                if self.device_type.MakeModel == MakeModel.GRIDWORKS__GW101:
                    if self.missing() and self.pico_uid:
                        self._send_to(
                            self.pico_cycler,
                            PicoMissing(ActorName=self.name, PicoHwUid=self.pico_uid),
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(
                                FromName=self.name, Channel=self.flow_channel
                            ),
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(
                                FromName=self.name, Channel=self.hot_temp_channel
                            ),
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(
                                FromName=self.name, Channel=self.cold_temp_channel
                            ),
                        )
                        if self.ct_channel:
                            self._send_to(
                                self.primary_scada,
                                ChannelFlatlined(
                                    FromName=self.name, Channel=self.ct_channel
                                ),
                            )
                        self.last_error_report = time.time()

            await asyncio.sleep(10)

import asyncio
import json
import math
import time
from functools import cached_property
from typing import Optional, Sequence

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gw.errors import DcError
from gwproactor import MonitoredName, Problems
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import PicoTankModuleComponent
from gwsproto.enums import TempCalcMethod
from gwsproto.enums import MakeModel
from gwsproto.named_types import SyncedReadings, TankModuleParams
from gwsproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from result import Ok, Result
from actors.sh_node_actor import ShNodeActor
from gwsproto.named_types import PicoMissing, ChannelFlatlined, MicroVolts

from scada_app_interface import ScadaAppInterface

R_FIXED_KOHMS = 5.65  # The voltage divider resistors in the TankModule
THERMISTOR_T0 = 298  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10  # The R0 of the NTC thermistor - an industry standard
PICO_VOLTS = 3.3
FLATLINE_REPORT_S = 60


class ApiTankModule(ShNodeActor):
    _stop_requested: bool
    _component: PicoTankModuleComponent

    def __init__(
        self,
        name: str,
        services:ScadaAppInterface,
    ):
        super().__init__(name, services)
        self._component = self.node.component
        
        if not isinstance(self._component, PicoTankModuleComponent):
            display_name = getattr(
                self._component.gt, "display_name", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> has type {type(self._component)}. "
                f"Expected PicoTankModuleComponent.\n"
                f"  Node: {self.name}\n"
                f"  Component id: {self.component.gt.ComponentId}"
            )
        self.device_type = self._component.cac
        if self.device_type.MakeModel != MakeModel.GRIDWORKS__TANKMODULE3:
            raise ValueError(f"Expect TankModule3  not {self.device_type.MakeModel}")
        self._stop_requested: bool = False

        if self._component.gt.Enabled:
            self._services.add_web_route(
                server_name=DEFAULT_WEB_SERVER_NAME,
                method="POST",
                path="/" + self.microvolts_path,
                handler=self._handle_microvolts_post,
            )
            self._services.add_web_route(
                server_name=DEFAULT_WEB_SERVER_NAME,
                method="POST",
                path="/" + self.params_path,
                handler=self._handle_params_post,
            )

        self.pico_uid = self._component.gt.PicoHwUid

        # Use the following for generating pico offline reports for triggering the pico cycler
        self.last_heard = time.time()
        self.last_error_report = time.time()
        tank_channel_names = (
            self.h0cn.buffer
            if self.name == self.h0n.buffer.reader
            else next(
                t for t in self.h0cn.tank.values()
                if t.reader == self.name
            )
        )

        if self.name == self.h0n.buffer.reader:
            self.depth_about_nodes: dict[int, str] = {
                1: self.h0n.buffer.depth1,
                2: self.h0n.buffer.depth2,
                3: self.h0n.buffer.depth3,
            }
        else:
            tank = next(
                t for t in self.h0n.tank.values()
                if t.reader == self.name
            )
            self.depth_about_nodes = {
                1: tank.depth1,
                2: tank.depth2,
                3: tank.depth3,
            }
        try:
            self.device_channels = {
                1: tank_channel_names.depth1_device,
                2: tank_channel_names.depth2_device,
                3: tank_channel_names.depth3_device,
            }
            if self._component.gt.SendMicroVolts:
                self.electrical_channels =  {
                    1: tank_channel_names.depth1_micro_v,
                    2: tank_channel_names.depth2_micro_v,
                    3: tank_channel_names.depth3_micro_v,
                }
        except KeyError as e:
            raise Exception(f"Problem setting up ApiTankModule channels! {e}")


    @cached_property
    def microvolts_path(self) -> str:
        return f"{self.name}/microvolts"

    @cached_property
    def params_path(self) -> str:
        return f"{self.name}/tank-module-params"

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

    def is_valid_pico_uid(self, params: TankModuleParams) -> bool:
        return (
                self._component.gt.PicoHwUid is None
                or self._component.gt.PicoHwUid == params.HwUid
            )

    def need_to_update_layout(self, params: TankModuleParams) -> bool:
        if self._component.gt.PicoHwUid:
            return False
        else:
            return True

    async def _handle_params_post(self, request: Request) -> Response:
        text = await self._get_text(request)
        self.params_text = text
        try:
            params = TankModuleParams(**json.loads(text))
        except BaseException as e:
            self._report_post_error(e, "malformed tankmodule parameters!")
            return Response()
        if params.ActorNodeName != self.name:
            return Response()

        if self.is_valid_pico_uid(params):
            cfg = next(
                (
                    cfg
                    for cfg in self._component.gt.ConfigList
                    if cfg.ChannelName ==  self.device_channels[1]
                ),
                None,
            )

            period = cfg.CapturePeriodS
            offset = round(period - time.time() % period, 3) - 2
            new_params = TankModuleParams(
                HwUid=params.HwUid,
                ActorNodeName=self.name,
                PicoAB=params.PicoAB,
                CapturePeriodS=cfg.CapturePeriodS,
                Samples=self._component.gt.Samples,
                NumSampleAverages=self._component.gt.NumSampleAverages,
                AsyncCaptureDeltaMicroVolts=self._component.gt.AsyncCaptureDeltaMicroVolts,
                CaptureOffsetS=offset,
            )
            if self.need_to_update_layout(params):
                self.pico_uid = params.HwUid
                self.log(f"UPDATE LAYOUT!!: In layout_gen, go to add_tank3 {self.name} "
                         f"and add PicoHwUid = '{params.HwUid}'")
            return Response(text=new_params.model_dump_json())
        else:
            # A strange pico is identifying itself as our "a" tank
            self.log(f"unknown pico {params.HwUid} identifying as {self.name}")
            # TODO: send problem report?
            return Response()

    async def _handle_microvolts_post(self, request: Request) -> Response:
        text = await self._get_text(request)
        self.readings_text = text
        if isinstance(text, str):
            try:
                self.services.send_threadsafe(
                    Message(
                        Src=self.name,
                        Dst=self.name,
                        Payload=MicroVolts(**json.loads(text)),
                    )
                )
            except Exception as e:  # noqa
                self._report_post_error(e, text)
        return Response()

    def _process_microvolts(self, data: MicroVolts) -> None:
        if data.HwUid != self.pico_uid:
            self.log(f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!")
            return

        self.last_heard = time.time()

        sensor_order = self._component.gt.SensorOrder or [1, 2, 3]
        channel_name_list: list[str] = []
        value_list: list[int] = []

        for logical_idx, physical_idx in enumerate(sensor_order):
            micro_volts = data.MicroVoltsList[logical_idx]
            device_channel = self.device_channels[physical_idx]
            volts = micro_volts / 1e6
            if volts <= 0:
                continue

            if self._component.gt.SendMicroVolts:
                channel_name_list.append(self.electrical_channels[physical_idx])
                value_list.append(micro_volts)
            if self._component.gt.TempCalcMethod == TempCalcMethod.SimpleBeta:
                try:
                    value_list.append(int(self.simple_beta(volts) * 1000))
                    channel_name_list.append(device_channel)
                except BaseException as e:
                    self.log(f"Problem with simple_beta({volts})! {e}")
                    self.send_error(f"Volts to temp problem for {device_channel}",
                                    details=str(e))
            else:
                raise Exception(f"No code for {self._component.gt.TempCalcMethod}!")
        msg = SyncedReadings(
            ChannelNameList=channel_name_list,
            ValueList=value_list,
            ScadaReadTimeUnixMs=int(time.time() * 1000),
        )
        self._send_to(self.pico_cycler, msg)
        self._send_to(self.primary_scada, msg)
        self._send_to(self.derived_generator, msg)

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        match message.Payload:
            case MicroVolts():
                self._process_microvolts(message.Payload)
        return Ok(True)

    def start(self) -> None:
        """IOLoop will take care of start."""
        self.services.add_task(
            asyncio.create_task(self.main(), name="ApiTankModule keepalive")
        )

    def stop(self) -> None:
        """IOLoop will take care of stop."""
        self._stop_requested = True

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

    def flatline_seconds(self) -> int:
        cfg = next(
            cfg
            for cfg in self._component.gt.ConfigList
            if cfg.ChannelName == self.device_channels[1]
        )
        return cfg.CapturePeriodS

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.flatline_seconds() * 2.1)]

    def missing(self) -> bool:
        return time.time() - self.last_heard > self.flatline_seconds()

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if self.last_error_report > FLATLINE_REPORT_S:
                if self.missing():
                    assert self.pico_uid
                    self._send_to(
                        self.pico_cycler,
                        PicoMissing(ActorName=self.name, PicoHwUid=self.pico_uid),
                    )
                    for ch in self.device_channels.values():
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(FromName=self.name, Channel=self.layout.data_channels[ch]),
                        )
                    for ch in self.electrical_channels.values():
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(FromName=self.name, Channel=self.layout.data_channels[ch]),
                        )

                    self.last_error_report = time.time()
            await asyncio.sleep(10)

    def simple_beta(self, volts: float, fahrenheit=False) -> float:
        """ Return temperature as a function of volts. Default Celsius. Use 
        standard beta function (self._component.gt.TempCalcMethod = TempCalcMethod.SimpleBeta)
        """
        if self._component.gt.TempCalcMethod != TempCalcMethod.SimpleBeta:
            raise Exception(f"Only call when TempCalcMethod is SimpleBeta, not {self._component.gt.TempCalcMethod }")
        r_therm = R_FIXED_KOHMS * volts/(PICO_VOLTS-volts)
        if r_therm <= 0:
            raise ValueError("Disconnected thermistor!")

        return self.temp_beta(r_therm, fahrenheit=fahrenheit)

    def temp_beta(self, r_therm_kohms: float, fahrenheit: bool = False) -> float:
        """
        beta formula specs for the Amphenol MA100GG103BN
        Uses T0 and R0 are a matching pair of values: this is a 10 K thermistor
        which means at 25 deg C (T0) it has a resistance of 10K Ohms

        [More info](https://drive.google.com/drive/u/0/folders/1f8SaqCHOFt8iJNW64A_kNIBGijrJDlsx)
        """
        t0, r0 = (
            THERMISTOR_T0,
            THERMISTOR_R0_KOHMS,
        )
        beta = self._component.gt.ThermistorBeta
        r_therm = r_therm_kohms
        temp_c = 1 / ((1 / t0) + (math.log(r_therm / r0) / beta)) - 273

        temp_f = 32 + (temp_c * 9 / 5)
        return round(temp_f, 2) if fahrenheit else round(temp_c, 2)

    def thermistor_resistance(self, volts):
        r_fixed = R_FIXED_KOHMS
        r_pico = self._component.gt.PicoKOhms
        if r_pico is None:
            raise DcError(f"{self.name} component missing PicoKOhms!")
        r_therm = 1 / ((3.3 / volts - 1) / r_fixed - 1 / r_pico)
        if r_therm <= 0:
            raise ValueError("Disconnected thermistor!")
        return r_therm

    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoRelated] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)
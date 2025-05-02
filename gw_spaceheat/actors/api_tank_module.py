import asyncio
import json
import math
import time
from functools import cached_property
from typing import List, Literal, Optional, Sequence

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gw.errors import DcError
from gwproactor import MonitoredName, Problems, AppInterface
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwproto.data_classes.components import PicoTankModuleComponent
from data_classes.house_0_names import H0N
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import TempCalcMethod
from gwproto.named_types import SyncedReadings, TankModuleParams
from gwproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from pydantic import BaseModel
from result import Ok, Result
from actors.scada_actor import ScadaActor
from named_types import PicoMissing, ChannelFlatlined

R_FIXED_KOHMS = 5.65  # The voltage divider resistors in the TankModule
THERMISTOR_T0 = 298  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10  # The R0 of the NTC thermistor - an industry standard

FLATLINE_REPORT_S = 60


class MicroVolts(BaseModel):
    HwUid: str
    AboutNodeNameList: List[str]
    MicroVoltsList: List[int]
    TypeName: Literal["microvolts"] = "microvolts"
    Version: Literal["100"] = "100"


class ApiTankModule(ScadaActor):
    _stop_requested: bool
    _component: PicoTankModuleComponent

    def __init__(
        self,
        name: str,
        services: AppInterface,
    ):
        super().__init__(name, services)
        component = services.hardware_layout.component(name)
        if not isinstance(component, PicoTankModuleComponent):
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
        self.pico_a_uid = self._component.gt.PicoAHwUid
        self.pico_b_uid = self._component.gt.PicoBHwUid
        # use the following for generate pico offline reports for triggering the pico cycler
        self.last_heard_a = time.time()
        self.last_heard_b = time.time()
        self.last_error_report = time.time()
        try:
            self.depth1_channel = self.layout.data_channels[f"{self.name}-depth1"]
            self.depth2_channel = self.layout.data_channels[f"{self.name}-depth2"]
            self.depth3_channel = self.layout.data_channels[f"{self.name}-depth3"]
            self.depth4_channel = self.layout.data_channels[f"{self.name}-depth4"]
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
        if params.PicoAB == "a":
            return (
                self._component.gt.PicoAHwUid is None
                or self._component.gt.PicoAHwUid == params.HwUid
            )
        elif params.PicoAB == "b":
            return (
                self._component.gt.PicoBHwUid is None
                or self._component.gt.PicoBHwUid == params.HwUid
            )
        return False

    def need_to_update_layout(self, params: TankModuleParams) -> bool:
        if params.PicoAB == "a":
            if self._component.gt.PicoAHwUid:
                return False
            else:
                return True
        elif params.PicoAB == "b":
            if self._component.gt.PicoBHwUid:
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
                    if cfg.ChannelName == f"{self.name}-depth1"
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
                if params.PicoAB == "a":
                    self.pico_a_uid = params.HwUid
                else:
                    self.pico_b_uid = params.HwUid
                self.log(f"UPDATE LAYOUT!!: In layout_gen, go to add_tank2 {self.name} "
                    f"and add Pico{params.PicoAB.capitalize()}HwUid = '{params.HwUid}'"
                )
                # TODO: send message to self so that writing to hardware layout isn't
                # happening in IO loop
            self.pico_state_log(f"{self.name}-{params.PicoAB}, {params.HwUid} ")
            return Response(text=new_params.model_dump_json())
        else:
            # A strange pico is identifying itself as our "a" tank
            self.log(f"unknown pico {params.HwUid} identifying as {self.name} Pico A!")
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
        if data.HwUid == self.pico_a_uid:
            self.last_heard_a = time.time()
        elif data.HwUid == self.pico_b_uid:
            self.last_heard_b = time.time()
        else:
            self.log(
                f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!"
            )
            return
        channel_name_list = []
        value_list = []
        for i in range(len(data.AboutNodeNameList)):
            volts = data.MicroVoltsList[i] / 1e6
            if self._component.gt.SendMicroVolts:
                value_list.append(data.MicroVoltsList[i])
                channel_name_list.append(f"{data.AboutNodeNameList[i]}-micro-v")
                #print(f"Updated {channel_name_list[-1]}: {round(volts,3)} V")
            if self._component.gt.TempCalcMethod == TempCalcMethod.SimpleBetaForPico:
                try:
                    value_list.append(int(self.simple_beta_for_pico(volts) * 1000))
                    channel_name_list.append(data.AboutNodeNameList[i])
                except BaseException as e:
                    self.services.send_threadsafe(
                        Message(
                            Payload=Problems(
                                msg=(
                                    f"Volts to temp problem for {data.AboutNodeNameList[i]}"
                                ),
                                errors=[e],
                            ).problem_event(
                                summary=(f"Volts to temp problem for {data.AboutNodeNameList[i]}"),
                            )
                        )
                    )
            else:
                raise Exception(f"No code for {self._component.gt.TempCalcMethod}!")
        msg = SyncedReadings(
            ChannelNameList=channel_name_list,
            ValueList=value_list,
            ScadaReadTimeUnixMs=int(time.time() * 1000),
        )
        self._send_to(self.pico_cycler, msg)
        self._send_to(self.primary_scada, msg)

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
            if cfg.ChannelName == f"{self.name}-depth1"
        )
        return cfg.CapturePeriodS

    @property
    def monitored_names(self) -> Sequence[MonitoredName]:
        return [MonitoredName(self.name, self.flatline_seconds() * 2.1)]

    def a_missing(self) -> bool:
        return time.time() - self.last_heard_a > self.flatline_seconds()

    def b_missing(self) -> bool:
        return time.time() - self.last_heard_b > self.flatline_seconds()

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if self.last_error_report > FLATLINE_REPORT_S:
                if self.a_missing():
                    self._send_to(
                        self.pico_cycler,
                        PicoMissing(ActorName=self.name, PicoHwUid=self.pico_a_uid),
                    )
                    self._send_to(
                        self.primary_scada,
                        ChannelFlatlined(FromName=self.name, Channel=self.depth1_channel)
                    )
                    self._send_to(
                        self.primary_scada,
                        ChannelFlatlined(FromName=self.name, Channel=self.depth2_channel)
                    )
                    self.last_error_report = time.time()
                if self.b_missing():
                    self._send_to(
                        self.pico_cycler,
                        PicoMissing(ActorName=self.name, PicoHwUid=self.pico_b_uid),
                    )
                    self._send_to(
                        self.primary_scada,
                        ChannelFlatlined(FromName=self.name, Channel=self.depth3_channel)
                    )
                    self._send_to(
                        self.primary_scada,
                        ChannelFlatlined(FromName=self.name, Channel=self.depth4_channel)
                    )
                    self.last_error_report = time.time()
            await asyncio.sleep(10)

    def simple_beta_for_pico(self, volts: float, fahrenheit=False) -> float:
        """
        Return temperature Celcius as a function of volts.
        Uses a fixed estimated resistance for the pico
        """
        r_therm_kohms = self.thermistor_resistance(volts)
        return self.temp_beta(r_therm_kohms, fahrenheit=fahrenheit)

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

    @property
    def pico_cycler(self) -> Optional[ShNode]:
        if H0N.pico_cycler in self.layout.nodes:
            return self.layout.nodes[H0N.pico_cycler]
        return None

    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoRelated] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)
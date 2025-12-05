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
from gwproto.data_classes.components import PicoTankModuleComponent
from gwproto.enums import TempCalcMethod
from gwproto.enums import MakeModel
from gwproto.named_types import SyncedReadings, TankModuleParams
from gwproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from result import Ok, Result
from actors.scada_actor import ScadaActor
from gwsproto.named_types import PicoMissing, ChannelFlatlined, MicroVolts

from scada_app_interface import ScadaAppInterface

R_FIXED_KOHMS = 5.65  # The voltage divider resistors in the TankModule
THERMISTOR_T0 = 298  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10  # The R0 of the NTC thermistor - an industry standard
PICO_VOLTS = 3.3
FLATLINE_REPORT_S = 60


class ApiTankModule(ScadaActor):
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
        if self.device_type.MakeModel not in [ MakeModel.GRIDWORKS__TANKMODULE2,
                                               MakeModel.GRIDWORKS__TANKMODULE3]:
            raise ValueError(f"Expect TankModule3 or TankModule2 .. not {self.device_type.MakeModel}")
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
        if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
            self.pico_uid = self._component.gt.PicoHwUid
        elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
            self.pico_a_uid = self._component.gt.PicoAHwUid
            self.pico_b_uid = self._component.gt.PicoBHwUid
        # Use the following for generating pico offline reports for triggering the pico cycler
        if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
            self.last_heard = time.time()
        elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
            self.last_heard_a = time.time()
            self.last_heard_b = time.time()
        self.last_error_report = time.time()
        try:
            self.depth1_channel = self.layout.data_channels[f"{self.name}-depth1"]
            self.depth2_channel = self.layout.data_channels[f"{self.name}-depth2"]
            self.depth3_channel = self.layout.data_channels[f"{self.name}-depth3"]
            if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
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
        if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
            return (
                self._component.gt.PicoHwUid is None
                or self._component.gt.PicoHwUid == params.HwUid
            )
        elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:  
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
        if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
            if self._component.gt.PicoHwUid:
                return False
            else:
                return True
        elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
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
                if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
                    self.pico_uid = params.HwUid
                    self.log(f"UPDATE LAYOUT!!: In layout_gen, go to add_tank3 {self.name} "
                         f"and add PicoHwUid = '{params.HwUid}'")
                elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
                    if params.PicoAB == "a":
                        self.pico_a_uid = params.HwUid
                    elif params.PicoAB == "b":
                        self.pico_b_uid = params.HwUid
                    pico_ab_string = params.PicoAB.capitalize()
                    self.log(f"UPDATE LAYOUT!!: In layout_gen, go to add_tank2 {self.name} "
                         f"and add Pico{pico_ab_string}HwUid = '{params.HwUid}'")
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
        if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
            if data.HwUid == self.pico_uid:
                self.last_heard = time.time()
            else:
                self.log(f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!")
                return
        elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
            if data.HwUid == self.pico_a_uid:
                self.last_heard_a = time.time()
            elif data.HwUid == self.pico_b_uid:
                self.last_heard_b = time.time()
            else:
                self.log(f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!")
                return
        channel_name_list = []
        value_list = []
        sensor_order = [1,2,3]
        if self._component.gt.SensorOrder is not None:
            sensor_order = self._component.gt.SensorOrder
        for i in range(len(data.AboutNodeNameList)):
            # Swapped thermistors
            if 'depth1' in data.AboutNodeNameList[i]:
                data.AboutNodeNameList[i] = data.AboutNodeNameList[i].replace('depth1', f'depth{sensor_order[0]}')
            elif 'depth2' in data.AboutNodeNameList[i]:
                data.AboutNodeNameList[i] = data.AboutNodeNameList[i].replace('depth2', f'depth{sensor_order[1]}')
            elif 'depth3' in data.AboutNodeNameList[i]:
                data.AboutNodeNameList[i] = data.AboutNodeNameList[i].replace('depth3', f'depth{sensor_order[2]}')

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
                    self.log(f"Problem with simple_beta({volts})! {e}")
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
            elif self._component.gt.TempCalcMethod == TempCalcMethod.SimpleBeta:
                try:
                    value_list.append(int(self.simple_beta(volts) * 1000))
                    channel_name_list.append(data.AboutNodeNameList[i])
                except BaseException as e:
                    self.log(f"Problem with simple_beta({volts})! {e}")
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
    
    def missing(self) -> bool:
        return time.time() - self.last_heard > self.flatline_seconds()

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if self.last_error_report > FLATLINE_REPORT_S:
                if self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE3:
                    if self.missing():
                        self._send_to(
                            self.pico_cycler,
                            PicoMissing(ActorName=self.name, PicoHwUid=self.pico_uid),
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(FromName=self.name, Channel=self.depth1_channel)
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(FromName=self.name, Channel=self.depth2_channel)
                        )
                        self._send_to(
                            self.primary_scada,
                            ChannelFlatlined(FromName=self.name, Channel=self.depth3_channel)
                        )
                        self.last_error_report = time.time()
                elif self.device_type.MakeModel == MakeModel.GRIDWORKS__TANKMODULE2:
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

    def simple_beta(self, volts: float, fahrenheit=False) -> float:
        """ Return temperature as a function of volts. Default Celcius. Use 
        standard beta function (self._component.gt.TempCalcMethod = TempCalcMethod.SimpleBeta)
        """
        if self._component.gt.TempCalcMethod != TempCalcMethod.SimpleBeta:
            raise Exception(f"Only call when TempCalcMethod is SimpleBeta, not {self._component.gt.TempCalcMethod }")
        r_therm = R_FIXED_KOHMS * volts/(PICO_VOLTS-volts)
        if r_therm <= 0:
            raise ValueError("Disconnected thermistor!")

        return self.temp_beta(r_therm, fahrenheit=fahrenheit)

    def simple_beta_for_pico(self, volts: float, fahrenheit=False) -> float:
        """
        Return temperature Celcius as a function of volts.
        Uses a fixed estimated resistance for the pico (self._component.gt.TempCalcMethod =TempCalcMethod.SimpleBetaForPico)
        SHOULD DEPRECATE WHEN NOT IN THE FIELD AS CALC IS INCORRECT
        """
        if self._component.gt.TempCalcMethod != TempCalcMethod.SimpleBetaForPico:
            raise Exception(f"Only call when TempCalcMethod is SimpleBetaForPico, not {self._component.gt.TempCalcMethod }")
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

    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoRelated] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)
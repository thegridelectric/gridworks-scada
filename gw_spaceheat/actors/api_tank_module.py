import asyncio
import json
import math
import time
from functools import cached_property
from typing import Optional, Sequence

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwsproto.errors import DcError
from gwproactor import MonitoredName, Problems
from gwproactor.message import PatInternalWatchdogMessage
from gwproto import Message
from gwsproto.data_classes.components import PicoTankModuleComponent, SimPicoTankModuleComponent
from gwsproto.enums import RelayClosedOrOpen, TempCalcMethod
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames
from gwsproto.named_types import SyncedReadings, TankModuleParams
from result import Ok, Result
from actors.pico_liveness import PicoLiveness
from actors.sh_node_actor import ShNodeActor
from gwsproto.data_classes.house_0_names import ScadaWeb
from gwsproto.named_types import PicoMissing, ChannelFlatlined, MicroVolts

from scada_app_interface import ScadaAppInterface

R_FIXED_KOHMS = 5.65  # The voltage divider resistors in the TankModule
THERMISTOR_T0 = 298  # i.e. 25 degrees
THERMISTOR_R0_KOHMS = 10  # The R0 of the NTC thermistor - an industry standard
PICO_VOLTS = 3.3
SIM_PICO_TICK_S = 1
# A tank at rest, stratified: depth1 is the top. Fixed until the plant drives
# tank temperatures.
SIM_TANK_AT_REST_C: dict[int, float] = {1: 55.0, 2: 50.0, 3: 45.0}


def microvolts_at_c(temp_c: float, beta: int) -> int:
    """The divider voltage the pico reads for a thermistor at temp_c, in
    microvolts: the inverse of simple_beta."""
    r_therm_kohms = THERMISTOR_R0_KOHMS * math.exp(
        beta * (1 / (temp_c + 273) - 1 / THERMISTOR_T0)
    )
    volts = PICO_VOLTS * r_therm_kohms / (R_FIXED_KOHMS + r_therm_kohms)
    return int(round(volts * 1e6))


class SimPicoSource:
    """A simulated pico tank module: a liveness stand-in, not a sensor.

    How it operates. The owning ApiTankModule ticks it once a second
    (SIM_PICO_TICK_S) and posts whatever it returns to itself, on the same
    path the web handler uses for a real pico's HTTP post. Each tick:

    - if the pico is dead and a reboot is due, it boots (the boot clock
      restarts);
    - if alive for SimLifeS since its boot, it dies (goes silent);
    - if alive and a capture period has passed since its last post, it
      returns one MicroVolts reading; otherwise nothing.

    Power follows the vdc relay: the actor feeds it every new state of that
    relay from the scada's latest machine states. An open kills it at once;
    the close that follows an open schedules a boot SimRebootS later. So a
    pico-cycler cycle (open, wait, close) revives it after SimRebootS, the
    way a real board rejoins wifi after a power cycle.

    What it is not. The reading is one fixed microvolt profile per depth (a
    tank at rest) that never moves and knows nothing of the plant; the death
    is on a fixed schedule, not a failure model; a reboot always succeeds,
    so zombies never arise on their own (SimRebootS absent is the only
    zombie path, a pico that stays dead); and nothing crosses HTTP, so the
    real ingress path is not exercised. SimLifeS and SimRebootS come from
    the layout's sim component (tlayouts emits 120 s and 20 s so a flatline
    and a cycle fit inside a five-minute run); either absent means absent:
    no scheduled death, no reboot. Pure: every method takes the current
    time, so a test drives it with no clock tricks."""

    def __init__(
        self,
        hw_uid: str,
        about_node_names: list[str],
        micro_volts: list[int],
        capture_period_s: int,
        life_s: Optional[int],
        reboot_s: Optional[int],
        booted_at: float,
    ) -> None:
        self.hw_uid = hw_uid
        self.about_node_names = about_node_names
        self.micro_volts = micro_volts
        self.capture_period_s = capture_period_s
        self.life_s = life_s
        self.reboot_s = reboot_s
        self.alive = True
        self.booted_at = booted_at
        self.last_post: Optional[float] = None
        self.relay_open_seen = False
        self.reboot_at: Optional[float] = None

    def relay_state(self, state: RelayClosedOrOpen, now: float) -> None:
        """Feed a vdc relay state change. Open cuts the pico's power; the
        close that follows schedules a reboot if SimRebootS is set."""
        if state == RelayClosedOrOpen.RelayOpen:
            self.alive = False
            self.reboot_at = None
            self.relay_open_seen = True
        elif self.relay_open_seen:
            self.relay_open_seen = False
            if self.reboot_s is not None:
                self.reboot_at = now + self.reboot_s

    def tick(self, now: float) -> Optional[MicroVolts]:
        """Advance to now; the reading to post, if one is due."""
        if not self.alive:
            if self.reboot_at is None or now < self.reboot_at:
                return None
            self.alive = True
            self.booted_at = now
            self.last_post = None
            self.reboot_at = None
        if self.life_s is not None and now - self.booted_at >= self.life_s:
            self.alive = False
            return None
        if self.last_post is not None and now - self.last_post < self.capture_period_s:
            return None
        self.last_post = now
        return MicroVolts(
            HwUid=self.hw_uid,
            AboutNodeNameList=self.about_node_names,
            MicroVoltsList=self.micro_volts,
        )


class ApiTankModule(ShNodeActor):
    """Reads a pico tank module over HTTP. When the component is the sim
    word the actor runs its own SimPicoSource, posting microvolts to itself
    on the same path the web handler uses. The source lives in the actor
    rather than as its own node or in the plant, a choice to re-evaluate: a
    plant-side pico posting over HTTP would test the real ingress path."""

    _stop_requested: bool

    def __init__(
        self,
        name: str,
        services:ScadaAppInterface,
    ):
        super().__init__(name, services)
        self._component = self.node.component
        
        if not isinstance(
            self._component,
            (PicoTankModuleComponent, SimPicoTankModuleComponent),
            ):
            display_name = getattr(
                self._component.gt, "DisplayName", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> has type {type(self._component)}. "
                f"Expected PicoTankModuleComponent or SimPicoTankModuleComponent.\n"
                f"  Node: {self.name}\n"
                f"  Component id: {self._component.gt.ComponentId}"
            )

        self._stop_requested: bool = False

        if self._component.gt.Enabled:
            self._services.add_web_route(
                server_name=ScadaWeb.DEFAULT_SERVER_NAME,
                method="POST",
                path="/" + self.microvolts_path,
                handler=self._handle_microvolts_post,
            )
            self._services.add_web_route(
                server_name=ScadaWeb.DEFAULT_SERVER_NAME,
                method="POST",
                path="/" + self.params_path,
                handler=self._handle_params_post,
            )

        self.pico_uid = self._component.gt.PicoHwUid

        self.liveness = PicoLiveness(
            expected_post_s=self.layout.capture_tuning_by_channel[
                f"{self.name}-depth1-device"
            ].CapturePeriodS
        )

        self.depth_about_nodes: dict[int, str] = {
            1: f"{self.name}-depth1",
            2: f"{self.name}-depth2",
            3: f"{self.name}-depth3",
        }
        self.device_channels: dict[int, str] = {
            1: f"{self.name}-depth1-device",
            2: f"{self.name}-depth2-device",
            3: f"{self.name}-depth3-device",
        }

        if self._component.gt.SendMicroVolts:
            self.electrical_channels: dict[int, str] = {
                1: f"{self.name}-depth1-micro-v",
                2: f"{self.name}-depth2-micro-v",
                3: f"{self.name}-depth3-micro-v",
            }

        self.sim_pico: Optional[SimPicoSource] = None
        if isinstance(self._component, SimPicoTankModuleComponent):
            assert self.pico_uid
            beta = self._component.gt.ThermistorBeta
            self.sim_pico = SimPicoSource(
                hw_uid=self.pico_uid,
                about_node_names=[self.depth_about_nodes[d] for d in (1, 2, 3)],
                micro_volts=[microvolts_at_c(SIM_TANK_AT_REST_C[d], beta) for d in (1, 2, 3)],
                capture_period_s=self.liveness.expected_post_s,
                life_s=self._component.gt.SimLifeS,
                reboot_s=self._component.gt.SimRebootS,
                booted_at=time.time(),
            )
        self.sim_relay_seen: Optional[tuple[str, int]] = None

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
            tuning = self.layout.capture_tuning_by_channel[self.device_channels[1]]

            period = tuning.CapturePeriodS
            offset = round(period - time.time() % period, 3) - 2
            new_params = TankModuleParams(
                HwUid=params.HwUid,
                ActorNodeName=self.name,
                PicoAB=params.PicoAB,
                CapturePeriodS=tuning.CapturePeriodS,
                Samples=self._component.gt.Samples,
                NumSampleAverages=self._component.gt.NumSampleAverages,
                AsyncCaptureDeltaMicroVolts=self._component.gt.AsyncCaptureDeltaMicroVolts,
                CaptureOffsetS=offset,
                PicoBoardVariant=params.PicoBoardVariant,
                MicropythonVersion=params.MicropythonVersion,
            )
            if self.need_to_update_layout(params):
                self.pico_uid = params.HwUid
                self.log(f"UPDATE LAYOUT!!: set PicoHwUid = '{params.HwUid}' on "
                         f"{self.name}'s tank component in the layout")
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
            self.log(
                f"{self.name}: Ignoring data from pico {data.HwUid} - not recognized!"
            )
            return

        self.liveness.heard(time.time())

        # SensorOrder: physical sensor index (1-based) -> correct physical depth
        sensor_order = self._component.gt.SensorOrder or [1, 2, 3]

        depth_map: dict[str, str] = {
            self.depth_about_nodes[i]: self.depth_about_nodes[sensor_order[i - 1]]
            for i in (1, 2, 3)
        }

        channel_name_list = []
        value_list = []
        for i, incoming_about in enumerate(data.AboutNodeNameList):
            correct_about_name = depth_map.get(incoming_about, incoming_about)
    
            volts = data.MicroVoltsList[i] / 1e6
            if self._component.gt.SendMicroVolts:
                value_list.append(data.MicroVoltsList[i])
                channel_name_list.append(f"{correct_about_name}-micro-v")
                #print(f"Updated {channel_name_list[-1]}: {round(volts,3)} V")
            if volts <= 0:
                continue
            elif self._component.gt.TempCalcMethod == TempCalcMethod.SimpleBeta:
                try:
                    value_list.append(int(self.simple_beta(volts) * 1000))
                    channel_name_list.append(f"{correct_about_name}-device") # channel names match node names
                except BaseException as e:
                    self.log(f"Problem with simple_beta({volts})! {e}")
                    self.services.send_threadsafe(
                        Message(
                            Payload=Problems(
                                msg=(
                                    f"Volts to temp problem for {correct_about_name}"
                                ),
                                errors=[e],
                            ).problem_event(
                                summary=(f"Volts to temp problem for {correct_about_name}"),
                            )
                        )
                    )
            else:
                raise Exception(f"No code for {self._component.gt.TempCalcMethod}!")

        if channel_name_list:
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
        if self.sim_pico is not None:
            self.services.add_task(
                asyncio.create_task(self.sim_pico_main(), name="ApiTankModule sim pico")
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

    def flatlined_channel_names(self) -> list[str]:
        names = list(self.device_channels.values())
        if self._component.gt.SendMicroVolts:
            names.extend(self.electrical_channels.values())
        return names

    def report_missing(self) -> None:
        assert self.pico_uid
        self._send_to(
            self.pico_cycler,
            PicoMissing(ActorName=self.name, PicoHwUid=self.pico_uid),
        )
        for ch in self.flatlined_channel_names():
            self._send_to(
                self.primary_scada,
                ChannelFlatlined(FromName=self.name, Channel=self.layout.data_channels[ch]),
            )

    async def main(self):
        while not self._stop_requested:
            self._send(PatInternalWatchdogMessage(src=self.name))
            if self.liveness.report_due(time.time()):
                self.report_missing()
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


    def pico_state_log(self, note: str) -> None:
        log_str = f"[PicoRelated] {note}"
        if self.settings.pico_cycler_state_logging:
            self.services.logger.error(log_str)
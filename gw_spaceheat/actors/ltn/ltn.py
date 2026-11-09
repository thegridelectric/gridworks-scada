import csv
import asyncio
from pathlib import Path
from datetime import datetime
from functools import cached_property
from typing import Any, Dict, List, Optional, Tuple, cast
from typing import Sequence

import numpy as np
import pytz
import aiohttp
import rich
import httpx

from gwproto.topic import MQTTTopic
from gwproto.messages import (
    Ack,
    Ping,
    ProblemEvent,
    ShutdownEvent,
    MQTTConnectEvent,
    MQTTConnectFailedEvent,
    MQTTDisconnectEvent,
    MQTTFullySubscribedEvent,
    ResponseTimeoutEvent,
    PeerActiveEvent,
)

from gwproactor import CodecFactory
from gwproactor import LinkSettings
from gwproactor import PrimeActor
from gwproactor import ProactorLogger
from gwproactor import ProactorName
from gwproactor import AppInterface
from clock import Clock
from ltn_app_interface import LtnAppInterface
from weather_source import ForecastPair
from gwproto import HardwareLayout
from gwproto import Message, MQTTCodec, create_message_model
from gwproto.messages import EventBase

from gwproactor import QOS
from gwproactor.config import LoggerLevels
from gwproactor.message import DBGCommands, DBGPayload, MQTTReceiptPayload

from gwsproto.conversions.temperature import convert_temp_to_f
from gwsproto.data_classes.hydronic_layout import HydronicLayout

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import (
    LogLevel,
    MarketPriceUnit, MarketQuantityUnit,
    TelemetryName, RelayClosedOrOpen, SeasonalStorageMode,
    SlowDispatchContractStatus, ServiceMode
)
from gwsproto.named_types import PowerWatts, Report, ReportEvent
from gwsproto.named_types import SendSnap, MachineStates
from actors.hydronic.store_temps import scrub_and_fill_store_temps
from actors.ltn.contract_handler import LtnContractHandler

from gwsproto.named_types import (
    Bid, FloOptimalPath, FloParams, FloRecommendation, FloRefusal, Glitch, HouseOperatingStatus, LatestPrice,
    LayoutLite, NoNewContractWarning, OperationalParams, SendLayout,
    SlowContractHeartbeat, SlowContractRejection,
    SnapshotSpaceheat, WaterStore,
)
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HSNN
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN

from paho.mqtt.client import MQTTMessageInfo
from pydantic import BaseModel


from actors.ltn.config import LtnSettings, DashboardSettings
from actors.ltn.dashboard.dashboard import Dashboard
from actors.ltn.data import LtnData
from actors.ltn.market import RJB, cleared_pair_index, market_slot_name, slot_is_current
from actors.ltn.flo_service import FLO_DST, flo_alias
from actors.ltn.flo_request import (
    PreviousRun,
    SeasonalFillForecast,
    StoreState,
    build_flo_params,
    load_previous_run,
    next_slot_start_s,
    previous_run_for,
    save_previous_run,
    seconds_to_slot_start,
)

try:
    from bruce.service import recommend_bytes
except ImportError:
    recommend_bytes = None  # type: ignore[assignment]

BRUCE_FLO_AVAILABLE = recommend_bytes is not None


class PriceForecast(BaseModel):
    dp_usd_per_mwh: List[float]
    lmp_usd_per_mwh: List[float]

    @property
    def total_energy(self) -> List[float]:
        """Calculate the total price forecast by summing dp and lmp components."""
        return [dp + lmp for dp, lmp in zip(self.dp_usd_per_mwh, self.lmp_usd_per_mwh)]


FORECAST_HOURS = 48


def price_forecast_from(
    timestamps: Sequence[float],
    dp_usd_per_mwh: Sequence[float],
    lmp_usd_per_mwh: Sequence[float],
    now_s: float,
) -> PriceForecast:
    """The next FORECAST_HOURS hours of a saved forecast as seen at `now_s`:
    hours already begun are dropped, and a forecast that ends early is
    extended by repeating its last hour."""
    keep = [i for i, t in enumerate(timestamps) if t > now_s]
    if not keep:
        raise ValueError("No forecasts available for the next hours!")
    dp = [dp_usd_per_mwh[i] for i in keep]
    lmp = [lmp_usd_per_mwh[i] for i in keep]
    short = FORECAST_HOURS - len(keep)
    if short > 0:
        dp = dp + [dp[-1]] * short
        lmp = lmp + [lmp[-1]] * short
    return PriceForecast(dp_usd_per_mwh=dp, lmp_usd_per_mwh=lmp)


class LtnMQTTCodec(MQTTCodec):
    """Decodes what reaches the LTN on its scada link: the scada's own
    messages, the maker's bare latest.price on its rjb topic, and the
    FLO's wrapped flo.recommendation or flo.refusal on the FLO's topics."""

    exp_src: str
    exp_dst: str = CoreNodeNames.ltn

    def __init__(self, hardware_layout: HydronicLayout):
        self.exp_src = hardware_layout.scada_g_node_alias
        self.flo_alias = flo_alias(hardware_layout.ltn_g_node_alias)
        super().__init__(
            create_message_model(
                model_name="LtnMessageDecoder",
                module_names=[
                    "gwsproto.named_types",
                    "gwproactor.message",
                ],
                explicit_types=[
                    Ack,
                    Ping,
                    ProblemEvent,
                    ShutdownEvent,
                    MQTTConnectEvent,
                    MQTTConnectFailedEvent,
                    MQTTDisconnectEvent,
                    MQTTFullySubscribedEvent,
                    ResponseTimeoutEvent,
                    PeerActiveEvent,
                ],
            )
        )

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if src not in (self.exp_src, self.flo_alias) or dst != self.exp_dst:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: {self.exp_src} or {self.flo_alias} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )

    def decode(self, topic: str, payload: bytes) -> Message[Any]:
        """A message on the maker's rjb broadcast topic is the bare
        latest.price word; everything else is a gw-wrapped message from
        the scada."""
        if topic.split("/")[0] == RJB:
            decoded_topic = MQTTTopic.decode(topic)
            if decoded_topic.remainder != ["mm", LatestPrice.model_fields["TypeName"].default]:
                raise ValueError(f"Unexpected rjb topic [{topic}]")
            return Message(
                Src=decoded_topic.src,
                Dst=self.exp_dst,
                Payload=LatestPrice.model_validate_json(payload),
            )
        return super().decode(topic, payload)

class LtnCodecFactory(CodecFactory):
    def get_codec(
        self,
        link_name: str,
        link: LinkSettings,
        proactor_name: ProactorName,
        layout: HardwareLayout,
    ) -> MQTTCodec:
        if not isinstance(layout, HydronicLayout):
            raise ValueError(
                "ERROR. ScadaCodecFactory requires hardware layout "
                "to be an instance of HydronicLayout but received layout type "
                f"<{type(layout)}>"
            )
        return LtnMQTTCodec(layout)


class Telemetry(BaseModel):
    Value: int
    Unit: TelemetryName


    
class Ltn(PrimeActor):
    MAIN_LOOP_SLEEP_SECONDS = 61
    HEARTBEAT_INTERVAL_S = 60
    SCADA_MQTT = "scada_mqtt"

    data: LtnData
    dashboard: Optional[Dashboard]
    _stop_requested: bool = False

    def __init__(self, name: str, services: AppInterface) -> None:
        super().__init__(name, services)
        # self._web_manager.disable()
        self.data = LtnData()
        self.latest_channel_values: Dict[str, int] = {}
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.flo_horizon_hours = self.settings.flo_horizon_hours
        self.flo_params: FloParams | None = None
        self.hp_is_off = False
        self.weather_forecast: Optional[ForecastPair] = None
        self.price_forecast: Optional[PriceForecast] = None
        self.data_channels: List
        self.tank_temp_channel_names = None
        self.latest_report: Optional[Report] = None
        self.report_output_dir = Path(f"{self.settings.paths.data_dir}/report")
        self.report_output_dir.mkdir(parents=True, exist_ok=True)
        self.recommendation: FloRecommendation | None = None
        self._previous_run_file = Path(f"{self.settings.paths.data_dir}/previous_run.json")
        self.previous_run: PreviousRun | None = load_previous_run(self._previous_run_file)

        if self.settings.dashboard.print_gui:
            self.dashboard = Dashboard(
                settings=self.settings.dashboard,
                ltn_g_node_alias=self.g_node_alias,
                data_channels=self.layout.channel_registry,
                logger=self.logger,
                thermostat_names=DashboardSettings.thermostat_names(
                    [channel.Name for channel in self.layout.data_channels.values()]
                ),
            )
        else:
            self.dashboard = None
        self.next_contract_energy_wh: Optional[int] = None
        self.contract_handler: LtnContractHandler = LtnContractHandler(
            node=self.node,
            settings=self.settings,
            layout=self.layout,
            logger=self.logger.add_category_logger(
                LtnContractHandler.LOGGER_NAME,
                level=self.settings.contract_rep_logging_level
            ),
            send_threadsafe=self.services.send_threadsafe,
        )
        # The loop wakes every MAIN_LOOP_SLEEP_SECONDS; a lead shorter than
        # that can pass between two wakes and the slot gets no bid.
        if self.settings.bid_lead_s <= self.MAIN_LOOP_SLEEP_SECONDS:
            raise ValueError(
                f"bid_lead_s ({self.settings.bid_lead_s}) must exceed the main "
                f"loop sleep ({self.MAIN_LOOP_SLEEP_SECONDS} s)"
            )
        self.bid_lead_s: int = self.settings.bid_lead_s
        # Gets strategy from scada sending LayoutLite
        self.layout_lite: Optional[LayoutLite] = None # Add this as a way of tracking if we've gotten the layout lite yet
        # TODO: read strategy from hardware layout: node = hardware_layout.node(...)
        self.buffer_flo = False
        # The posture facts ride gw.house.operating.status, the LTN's one source;
        # until the first one arrives the LTN refuses to dispatch.
        self.operating_status: Optional[HouseOperatingStatus] = None
        self.accepts_dispatch: bool = False
        self.service_mode: ServiceMode = ServiceMode.Heating
        self.seasonal_storage_mode: SeasonalStorageMode = SeasonalStorageMode.AllTanks
        self.keep_buffer_full: bool = self.settings.keep_buffer_full

    @classmethod
    def get_codec_factory(cls) -> LtnCodecFactory:
        return LtnCodecFactory()

    @property
    def logger(self) -> ProactorLogger:
        return self.services.logger

    @cached_property
    def short_name(self) -> str:
        return self.services.subscription_name

    @property
    def node(self) -> ShNode:
        return self.layout.node(self.name)

    @property
    def scada(self) -> ShNode:
        return self.layout.node(CoreNodeNames.primary_scada)

    @property
    def publication_name(self) -> str:
        return self.services.publication_name

    @property
    def subscription_name(self) -> str:
        return self.services.subscription_name

    @property
    def settings(self) -> LtnSettings:
        return cast(LtnSettings, self.services.settings)

    @property
    def layout(self) -> HydronicLayout:
        return cast(HydronicLayout, self.services.hardware_layout)

    @property
    def g_node_alias(self) -> str:
        """This LTN's GNode alias."""
        return self.layout.ltn_g_node_alias

    @property
    def app(self) -> LtnAppInterface:
        if not isinstance(self.services, LtnAppInterface):
            raise RuntimeError(f"The LTN runs under an LtnAppInterface, not {type(self.services).__name__}")
        return self.services

    @property
    def plant_clock(self) -> Clock:
        return self.app.clock

    @property
    def ops(self) -> OperationalParams:
        return self.app.operational_params

    @property
    def water_store(self) -> WaterStore:
        store = self.layout.hydronic.WaterStore
        if store is None:
            raise RuntimeError(f"Layout {self.g_node_alias} has no water store to run a FLO on")
        return store

    def _publish_to_scada(self, payload, qos: QOS = QOS.AtMostOnce) -> MQTTMessageInfo:
        return self.services.publish_message(
            Ltn.SCADA_MQTT, Message(Src=self.publication_name, Payload=payload), qos=qos
        )

    def _message_for_scada_publish(self, payload: GwsprotoSemaType) -> None:
        """A gw-wrapped copy of a word to the scada over MQTT (OPS-387), the
        interim path until the LTN is a gwbase actor broadcasting on rjb."""
        self.services.publish_message(
            self.SCADA_MQTT,
            Message(Src=self.publication_name, Dst=self.scada.name, Payload=payload),
        )

    def process_internal_message(self, message: Message):
        path_dbg = 0
        self.logger.path(
            "++Ltn.process_internal_message %s/%s",
            message.Header.Src,
            message.Header.MessageType,
        )
        if message.Header.Dst == self.scada.name:
            path_dbg |= 0x00000001
            self._publish_to_scada(message.Payload)
        else:
            path_dbg |= 0x00000002
            self.process_ltn_message(message)
        self.logger.path("--Ltn.process_internal_message  path:0x%08X",path_dbg)


    def process_ltn_message(self, message: Message):
        self.logger.path(
            "++Ltn.process_ltn_message %s/%s",
            message.Header.Src,
            message.Header.MessageType,
        )
        path_dbg = 0
        match message.Payload:
            case Glitch():
                path_dbg |= 0x00000002
                self._message_for_scada_publish(message.Payload)
            case _:
                path_dbg |= 0x00000008
        self.logger.path("--Ltn._derived_process_message  path:0x%08X", path_dbg)

    def process_mqtt_message(
        self, message: Message[MQTTReceiptPayload], decoded: Any
    ):
        self.logger.path(
            "++Ltn.process_mqtt_message %s", message.Payload.message.topic
        )
        path_dbg = 0
        if message.Payload.client_name != self.SCADA_MQTT:
            raise ValueError(
                f"There are no messages expected to be received from [{message.Payload.client_name}] mqtt broker. "
                f"Received\n\t topic: [{message.Payload.message.topic}]"
            )
        match decoded.Payload:
            case LayoutLite():
                path_dbg |= 0x00000001
                self.process_layout_lite(decoded.Payload)
            case HouseOperatingStatus():
                path_dbg |= 0x00000001
                self.process_house_operating_status(decoded.Payload)
            case NoNewContractWarning():
                path_dbg |= 0x00000002
                self.process_no_new_contract_warning(decoded.Payload)
            case PowerWatts():
                path_dbg |= 0x00000004
                self.process_power_watts(decoded.Payload)
            case Report():
                path_dbg |= 0x00000008
                self.process_report(decoded.Payload)
            case SnapshotSpaceheat():
                path_dbg |= 0x00000020
                self.process_snapshot(decoded.Payload)
            case SlowContractHeartbeat():
                self.contract_handler.process_slow_contract_heartbeat(decoded.Payload)
            case SlowContractRejection():
                self.contract_handler.process_slow_contract_rejection(decoded.Payload)
            case FloRecommendation():
                path_dbg |= 0x00000800
                self.process_flo_recommendation(decoded.Payload)
            case FloRefusal():
                path_dbg |= 0x00001000
                self.process_flo_refusal(decoded.Payload)
            case LatestPrice():
                path_dbg |= 0x00000400
                if decoded.Header.Src == self.ops.MarketMakerAlias:
                    self.process_latest_price(decoded.Payload)
                else:
                    self.log(
                        f"Ignoring latest.price from {decoded.Header.Src}: "
                        f"the market maker is {self.ops.MarketMakerAlias}"
                    )
            case EventBase():
                path_dbg |= 0x00000040
                self._process_event(decoded.Payload)
                if (
                    decoded.Payload.TypeName
                    == ReportEvent.model_fields["TypeName"].default
                ):
                    path_dbg |= 0x00000080
                    self.process_report(decoded.Payload.Report)
                elif (
                    decoded.Payload.TypeName
                    == SnapshotSpaceheat.model_fields["TypeName"].default
                ):
                    path_dbg |= 0x00000100
                    self.process_snapshot(decoded.Payload)
            case _:
                path_dbg |= 0x00000200
        self.logger.path("--Ltn.process_mqtt_message  path:0x%08X", path_dbg)

    def process_no_new_contract_warning(self, payload: NoNewContractWarning) -> None:
        """
        Resending a "Created" hb if it exists
        """
        hb = self.contract_handler.latest_hb
        if hb:
            if hb.Status == SlowDispatchContractStatus.Created:
                self.services.send_threadsafe(
                    Message(
                        Src=self.name,
                        Dst=self.scada.name,
                        Payload=hb
                    )
                )

    def process_power_watts(self, pwr: PowerWatts) -> None:

        self.data.latest_power_w = pwr.Watts
        if not self.dashboard:
            return

        if self.settings.dashboard.print_gui:
            self.dashboard.process_power(pwr)
        else:
            rich.print("Received PowerWatts")
            rich.print(pwr)

    def snapshot_str(self, snapshot: SnapshotSpaceheat) -> str:
        s = "\n\nSnapshot received:\n"
        for single_reading in snapshot.LatestReadingList:
            channel = self.layout.data_channels[single_reading.ChannelName]
            try:
                temperature = self.layout.channel_registry.temperature(
                    channel.Name, single_reading.Value
                )
            except ValueError:
                extra = f"{single_reading.Value} {channel.TelemetryName}"
            else:
                if self.settings.c_to_f:
                    extra = f"{temperature.f:5.2f} F"
                else:
                    extra = f"{temperature.c:5.2f} C"
            s += f"  {channel.AboutNodeName}: {extra}\n"
        return s

    def process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        self.data.latest_snapshot = snapshot

        if self.settings.dashboard.print_gui and self.dashboard:
            self.dashboard.process_snapshot(snapshot)
        if self.settings.dashboard.print_snap:
            self.logger.warning(self.snapshot_str(snapshot))
        for reading in snapshot.LatestReadingList:
            self.latest_channel_values[reading.ChannelName] = reading.Value

    def process_house_operating_status(self, status: HouseOperatingStatus) -> None:
        """The scada's slow operating facts: the LTN bids and runs FLOs only
        while the house accepts dispatch and serves heat, and sizes the FLO
        by the storage mode."""
        self.log(f"Operating status: {status}")
        self.operating_status = status
        self.accepts_dispatch = status.AcceptsDispatch
        self.service_mode = status.ServiceMode
        self.seasonal_storage_mode = status.SeasonalStorageMode
        self.log(f"FLO seasonal storage mode: {self.seasonal_storage_mode}")

    def process_layout_lite(self, layout: LayoutLite) -> None:
        """ ContractState: Initializing -> Ready if needed
        """
        self.log("Processing layout lite")
        self.logger.info(f"Processing layout lite: {layout}")
        self.layout_lite = layout

        self.tank_temp_channel_names = list(HCN.buffer.effective)
        for tank_idx in sorted(self.layout.store_tanks):
            tank = self.layout.store_tanks[tank_idx]
            self.tank_temp_channel_names.extend([tank.depth1, tank.depth2, tank.depth3])

        if self.contract_handler.layout_received is False:
            self.contract_handler.layout_received = True # Necessary for bids & contracts
            self.log("Received layout data - LTN now ready for contract operations")

    def process_report(self, report: Report) -> None:
        self.data.latest_report = report
        # Check if HP is on or off by looking at relay 6
        for machine_state in report.StateList:
            ms : MachineStates = machine_state
            if HSNN.hp_scada_ops_relay in ms.MachineHandle:
                if ms.StateList[-1] == RelayClosedOrOpen.RelayOpen:
                    self.hp_is_off = True
                else:
                    self.hp_is_off = False
        if self.settings.save_events:
            report_file = (
                self.report_output_dir / f"Report.{report.SlotStartUnixS}.json"
            )
            with report_file.open("w") as f:
                f.write(str(report))

    def _process_event(self, event: EventBase) -> None:
        if self.settings.save_events:
            timezone = pytz.timezone("America/New_York")
            event_dt = datetime.fromtimestamp(event.TimeCreatedMs / 1000, tz=timezone)
            event_file = Path(
                f"{self.settings.paths.event_dir}/{event_dt.isoformat()}.{event.TypeName}.uid[{event.MessageId}].json"
            )
            with event_file.open("w") as f:
                f.write(event.model_dump_json(indent=2))

    def snap(self):
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SendSnap(
                    FromGNodeAlias=self.g_node_alias,
                ),
            )
        )

    def send_layout(self) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SendLayout(
                    FromGNodeAlias=self.g_node_alias,
                    MessageCreatedMs=self.plant_clock.now_ms()
                ),
            )
        )
        self.log("Requesting layout")

    def start_tasks(self) -> Sequence[asyncio.Task[Any]]:
        return  [
            asyncio.create_task(self.main(), name="ltn-main"),
            asyncio.create_task(
                self.contract_handler.contract_heartbeat_task(),
                name="contract_heartbeat"
            ),
        ]

    async def main(self):
        async with aiohttp.ClientSession() as session:
            await self.main_loop(session)

    async def main_loop(self, session: aiohttp.ClientSession) -> None:
        await asyncio.sleep(5)
        self.send_layout()

        while not self._stop_requested:
            if not self.accepts_dispatch or self.service_mode != ServiceMode.Heating:
                # SCADA-side: plant is not accepting heating intent
                if self.operating_status is None:
                    self.log(
                        "Main loop idle: waiting for gw.house.operating.status from SCADA "
                        "(accepts_dispatch stays false until then)"
                    )
                else:
                    self.log(
                        f"Main loop idle: accepts_dispatch={self.accepts_dispatch}, "
                        f"service_mode={self.service_mode.value} "
                        "(need accepts_dispatch and Heating to run FLO)"
                    )
                await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)
                continue

            # One request to the FLO per slot, bid_lead_s before it starts:
            # the store is measured then, the FLO answers over the broker,
            # and the bid goes off the answer. The request stays until the
            # next slot's replaces it, so the answer and the clearing price
            # at the slot start both find it.
            now_s = self.plant_clock.now()
            slot_start_s = next_slot_start_s(now_s)
            to_slot_s = seconds_to_slot_start(now_s)
            if to_slot_s > self.bid_lead_s:
                self.log(
                    f"Waiting until {self.bid_lead_s} s before the slot to ask "
                    f"the FLO ({to_slot_s} s to go)."
                )
            elif self.flo_params is not None and self.flo_params.StartUnixS == slot_start_s:
                self.log(f"Already asked the FLO for slot {slot_start_s}.")
            else:
                try:
                    await self.ask_the_flo(session, slot_start_s)
                except Exception as e:
                    self.logger.exception("[ltn] Exception asking the FLO! %s", e)
                    self.log(f"Exception asking the FLO! {e!r}")

            if self.contract_handler.latest_hb is None:
                self.log("No active contract.")

            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    async def ask_the_flo(self, session: aiohttp.ClientSession, slot_start_s: int) -> None:
        """Build the request for the slot and send it to the FLO.

        Async because it fetches the forecasts. The FLO's answer arrives
        on the scada link as a flo.recommendation, which
        `process_flo_recommendation` turns into the bid.
        """
        await self.get_weather(session)
        await self.get_price_forecast()

        if not self.layout_lite:
            self.log("Do not have layout lite from scada so not running the FLO... must not be connected!!")
            return

        if not self.accepts_dispatch or self.service_mode != ServiceMode.Heating:
            # A known, occasional race: the main loop checked this before
            # calling, and the scada's posture changed while the forecasts
            # were fetched. Logged, not a glitch; nothing is wrong.
            self.log(
                f"Not asking the FLO for slot {slot_start_s}: the scada no "
                f"longer accepts dispatch in Heating mode."
            )
            return

        self.log("Finding thermocline position and top temperature")
        result = await self.get_three_layer_storage_model()
        self.log(f"{self.seasonal_storage_mode.value} model: {result}")

        if result is None:
            self.log("Get thermocline and centroid failed! Not running FLO!")
            return
        t, m, b, th1, th2 = result

        buffer_available_kwh = await self.get_buffer_available_kwh()
        if self.price_forecast is None:
            self.log("Not running flo - no price forecast")
            return
        if self.weather_forecast is None:
            self.log("Not running flo - no weather forecast")
            return
        try:
            self.flo_params = build_flo_params(
                ops=self.ops,
                water_store=self.water_store,
                storage_mode=self.seasonal_storage_mode,
                forecast=self.weather_forecast,
                now_s=self.plant_clock.now(),
                horizon_hours=self.flo_horizon_hours,
                lmp_usd_mwh=self.price_forecast.lmp_usd_per_mwh,
                dist_usd_mwh=self.price_forecast.dp_usd_per_mwh,
                store=StoreState(t, m, b, th1, th2, hp_on=not self.hp_is_off),
                buffer_available_kwh=buffer_available_kwh,
                g_node_alias=self.g_node_alias,
                start_unix_s=slot_start_s,
                created_ms=int(self.plant_clock.now() * 1000),
                previous=previous_run_for(self.previous_run, slot_start_s),
            )
        except SeasonalFillForecast as e:
            self.log(f"Not running flo - {e}")
            return
        self.log(f"FloParams:\n {self.flo_params.model_dump_json(by_alias=True)}\n")
        self.log(f"Settings ask for a {self.flo_horizon_hours} hour horizon; using {len(self.flo_params.StepDurationMinutes)}")
        self.send_flo_params(self.flo_params)

    def send_flo_params(self, params: FloParams) -> None:
        """The request to the FLO, gw-wrapped on the scada broker and
        addressed to the flo class, and a copy to the scada for the record."""
        self._message_for_scada_publish(params)
        self.services.publish_message(
            self.SCADA_MQTT,
            Message(Src=self.publication_name, Dst=FLO_DST, Payload=params),
        )
        self.log(f"Asked the FLO for slot {params.StartUnixS}")

    def process_flo_recommendation(self, recommendation: FloRecommendation) -> None:
        """The FLO's answer. One that answers the request held becomes the
        bid: it is kept for the price that clears, copied to the scada for
        the record, and the bid goes to the maker. One for another bidder
        or slot, or a second answer to the same request, is dropped."""
        slot_start_s = recommendation.OptimalPathList[0].StartUnixS
        if self.flo_params is None:
            self.log(f"Dropping a flo.recommendation for slot {slot_start_s}: no request held")
            return
        if (
            recommendation.BidderAlias != self.flo_params.GNodeAlias
            or slot_start_s != self.flo_params.StartUnixS
        ):
            self.log(
                f"Dropping a flo.recommendation for {recommendation.BidderAlias} slot "
                f"{slot_start_s}: the request held is for {self.flo_params.GNodeAlias} "
                f"slot {self.flo_params.StartUnixS}"
            )
            return
        if (
            self.recommendation is not None
            and self.recommendation.OptimalPathList[0].StartUnixS == slot_start_s
        ):
            self.log(f"Dropping a second flo.recommendation for slot {slot_start_s}")
            return
        self.recommendation = recommendation
        self._message_for_scada_publish(recommendation)
        self.log(f"FLO answered slot {slot_start_s}: {len(recommendation.PqPairs)} PQ pairs.")
        bid = Bid(
            BidderAlias=self.flo_params.GNodeAlias,
            MarketSlotName=market_slot_name(self.ops, self.flo_params.StartUnixS),
            PqPairs=list(recommendation.PqPairs),
            InjectionIsPositive=True,
            PriceUnit=MarketPriceUnit.USDPerMWh,
            QuantityUnit=MarketQuantityUnit.AvgkW,
            SignedMarketFeeTxn="BogusAlgoSignature",
        )
        self.contract_handler.latest_bid = bid
        self.services.publish_message(
            self.SCADA_MQTT,
            # Address the MarketMaker. "mm" is deliberately the gwbase
            # RoutingClass.MarketMaker token, so the wire key
            # gw.<src>.to.mm.<type> already matches the new/future rabbit
            # structure and resolves to TransportClass.MarketMaker — i.e. we
            # code to the gwbase transport encoding now. HACK (interim): it's
            # hard-coded because H0N has no MM node (the MM is external to the
            # scada lexicon); derive it once the LTN is a gwbase actor. OPS-387.
            Message(Src=self.publication_name, Dst="mm", Payload=bid)
        )
        self.log(f"Bid: {bid}")

    def process_flo_refusal(self, refusal: FloRefusal) -> None:
        """The FLO's answer that there is no recommendation. One for the
        request held is copied to the scada for the record and raised as a
        Warning glitch, so the fleet sees why the slot has no FLO bid; the
        LTN bids as it does when no answer comes. One for another bidder
        or slot is dropped."""
        if (
            self.flo_params is None
            or refusal.BidderAlias != self.flo_params.GNodeAlias
            or refusal.StartUnixS != self.flo_params.StartUnixS
        ):
            self.log(
                f"Dropping a flo.refusal for {refusal.BidderAlias} slot "
                f"{refusal.StartUnixS}: not the request held"
            )
            return
        self._message_for_scada_publish(refusal)
        summary = f"FLO refused slot {refusal.StartUnixS}: {refusal.Reason.value}"
        self.log(f"{summary}, {refusal.Detail}")
        glitch = Glitch(
            FromGNodeAlias=self.g_node_alias,
            Node=self.node.name,
            Type=LogLevel.Warning,
            Summary=summary,
            Details=refusal.Detail or "",
            CreatedMs=self.plant_clock.now_ms(),
        )
        self.services.send_threadsafe(Message(Src=self.name, Dst=self.name, Payload=glitch))

    def stop(self) -> None:
        self._stop_requested = True
        super().stop()

    def latest_contract_is_live(self) -> bool:
        """ Validates that the bid's market slot name corresponds to the current hour."""
        bid = self.contract_handler.latest_bid
        if not bid:
            return False
            
        try:
            if not slot_is_current(bid.MarketSlotName, self.plant_clock.now()):
                self.log(f"Bid time mismatch: bid for {bid.MarketSlotName} is not for the current hour")
                return False
            return True
        except (ValueError, IndexError) as e:
            self.log(f"Error validating bid time: {e}")
            return False

    def process_latest_price(self, payload: LatestPrice) -> None:
        self.contract_handler.latest_price = payload
        self.log("Received latest price")
        if self.contract_handler.latest_bid is None:
            self.log("Ignoring - no bid exists")
            return

        # Validate bid timeframe
        if not self.latest_contract_is_live():
            glitch = Glitch(
                FromGNodeAlias=self.g_node_alias,
                Node=self.node.name,
                Type=LogLevel.Warning,
                Summary="Invalid bid timeframe",
                Details=f"Stale bid detected. Bid slot start: {self.contract_handler.latest_bid.MarketSlotName}. Current price: {payload.MarketSlotName}",
                CreatedMs=self.plant_clock.now_ms()
            )
            self.contract_handler.latest_bid = None
            self.services.send_threadsafe(
                Message(Src=self.name, Dst=self.name, Payload=glitch))
            self.log("Sent glitch for invalid bid timeframe and set latest bid to None")
            return
        
        if (
            datetime.now(self.timezone).minute != 0
            and datetime.now(self.timezone).second <= 5
        ):
            self.log(
                "The latest price was not received within the first 5 seconds of the hour. Abort."
            )
            return

        pq_pairs = self.contract_handler.latest_bid.PqPairs
        self.log(f"Sorted pq pairs: {sorted((x.PriceX1000, x.QuantityX1000) for x in pq_pairs)} (x1000)")
        self.log(f"Payload price: {payload.PriceTimes1000} (x1000)")
        # Quantity is AvgkW, so QuantityX1000 is avg_w
        assert self.contract_handler.latest_bid.QuantityUnit == MarketQuantityUnit.AvgkW
        cleared = cleared_pair_index(pq_pairs, payload.PriceTimes1000)
        avg_w = pq_pairs[cleared].QuantityX1000
        self.log(f"Decided on quantity: {avg_w} WattHours")
        self.keep_cleared_path(cleared)

        # 1 hour
        self.contract_handler.next_contract_energy_wh = avg_w * 1
        if self.contract_handler.next_contract_energy_wh < 1000:
            self.contract_handler.next_contract_energy_wh = 0

        if self.contract_handler.latest_hb:
            self.contract_handler.start_completing_old_contract()
        elif self.contract_handler.can_create_contract():
            self.contract_handler.create_new_contract()
        else:
            self.log("Why am I here")

    def keep_cleared_path(self, cleared: int) -> None:
        """The path the cleared pair leads to, with the price the request
        forecast for the slot after it: saved as the next run's previous
        run, and copied to the scada for the record."""
        if self.recommendation is None or self.flo_params is None:
            self.log("No recommendation held for this slot; no previous run for the next")
            return
        path: FloOptimalPath = self.recommendation.OptimalPathList[cleared]
        if path.StartUnixS != self.flo_params.StartUnixS:
            self.log(
                f"Recommendation is for slot {path.StartUnixS}, the request for "
                f"{self.flo_params.StartUnixS}; no previous run for the next"
            )
            return
        self.previous_run = PreviousRun(
            path=path,
            elec_usd_mwh_now=float(self.flo_params.LmpUsdMwhList[1] + self.flo_params.DistUsdMwhList[1]),
        )
        save_previous_run(self._previous_run_file, self.previous_run)
        self._message_for_scada_publish(path)
        self.log(f"Kept the cleared path: {path.HpAvgWList[:6]} W, store {path.StoreWhList[:6]} Wh")

    def fill_missing_store_temps(self) -> None:
        """Scrub implausible store layers and fill the missing ones from
        below (`store_temps.scrub_and_fill_store_temps`, the pass the
        scada runs too)."""
        all_store_layers = sorted(
            [x for x in self.tank_temp_channel_names if "tank" in x]
        )
        scrub_and_fill_store_temps(self.latest_temps_f, all_store_layers, HCN.store_cold_pipe)
        self.latest_temps_f = {
            k: self.latest_temps_f[k] for k in sorted(self.latest_temps_f)
        }

    def get_latest_temperatures(self):
        if self.tank_temp_channel_names is None:
            self.temperatures_available = False
            self.log("Can't get latest temperatures, don't have temperature channel names!")
            return
        temps = {}
        for ch_name in self.tank_temp_channel_names:
            raw = self.latest_channel_values.get(ch_name)
            if raw is None:
                continue
            try:
                unit = self.layout.channel_registry.unit(ch_name)
                if unit is None:
                    raise Exception(
                        f"temperature channels should have units! {ch_name}"
                    )
                temp_f = convert_temp_to_f(
                    raw=raw,
                    encoding=unit
                )
            except Exception as e:
                note = f"Temperature conversion failed for {ch_name}: {e}"
                self.log(note)
                continue
            temps[ch_name] = temp_f

        self.latest_temps_f = temps.copy()
        self.fill_missing_store_temps()
        self.temperatures_available = set(self.tank_temp_channel_names) <= self.latest_temps_f.keys()

    async def get_RSWT(self, minus_deltaT=False):
        if self.weather_forecast is None:
            raise Exception("weather_forecast cannot be None here!")
        try:
            curve = self.ops.HeatingCurve
            alpha = curve.AlphaTimes10 / 10
            beta = curve.BetaTimes100 / 100
            gamma = curve.GammaEx6 / 1e6
            weather = self.weather_forecast.next_hours(1, self.plant_clock.now())
            oat = weather.oat_f[0]
            ws = weather.wind_speed_mph[0]
            r = alpha + beta*oat + gamma*ws*(65-oat)
            rhp= r if r>0 else 0
            intermediate_rswt = curve.IntermediateRswtF
            dd_rswt = curve.DdRswtF
            intermediate_power = curve.IntermediatePowerKw
            dd_power = curve.DdPowerKw
            no_power_rswt = -alpha/beta
            x_rswt = np.array([no_power_rswt, intermediate_rswt, dd_rswt])
            y_hpower = np.array([0, intermediate_power, dd_power])
            A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
            a, b, c = np.linalg.solve(A, y_hpower)
            c2 = c - rhp
            rswt = round((-b + (b**2-4*a*c2)**0.5)/(2*a),2)
            deltaT = curve.DdDeltaTF/curve.DdPowerKw * (a*rswt**2 + b*rswt + c)
            deltaT = deltaT if deltaT>0 else 0
            if minus_deltaT:
                return rswt - deltaT
            return rswt
        except Exception:
            self.log("Could not find RSWT!")
            return None

    async def kmeans(self, data, k=3, max_iters=100, tol=1e-4):
        data = np.array(data).reshape(-1, 1)
        centroids = data[np.random.choice(len(data), k, replace=False)]
        for _ in range(max_iters):
            labels = np.argmin(np.abs(data - centroids.T), axis=1)
            new_centroids = np.zeros_like(centroids)
            for i in range(k):
                cluster_points = data[labels == i]
                if len(cluster_points) > 0:
                    new_centroids[i] = cluster_points.mean()
                else:
                    new_centroids[i] = data[np.random.choice(len(data))]
            if np.all(np.abs(new_centroids - centroids) < tol):
                break
            centroids = new_centroids
        return labels

    async def get_three_layer_storage_model(self) -> Optional[Tuple[float, float, float, int, int]]:
        # Get all storage tank temperatures in a dict
        if self.tank_temp_channel_names is None:
            self.send_layout()
            await asyncio.sleep(5)
        self.get_latest_temperatures()
        if not self.temperatures_available:
            self.log("Not enough tank temperatures available to compute top temperature and thermocline!")
            return None
        all_layers = sorted(
            [x for x in self.tank_temp_channel_names if ("buffer" if self.seasonal_storage_mode == SeasonalStorageMode.BufferOnly else "tank") in x]
        )
        try:
            tank_temps = {
                key: self.latest_temps_f[key]
                for key in all_layers
            }
        except KeyError as e:
            self.log(f"Failed to get all the tank temps in get_three_layer_storage_model! Bailing on process {e}")
            return None

        if self.seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            top_temp = round(tank_temps[HCN.buffer.depth1],1)
            middle_temp = round(tank_temps[HCN.buffer.depth2],1)
            bottom_temp = round(tank_temps[HCN.buffer.depth3],1)
            thermocline1 = 1
            thermocline2 = 2
            return top_temp, middle_temp, bottom_temp, thermocline1, thermocline2

        # Process layer temperatures
        layer_temps = [tank_temps[key] for key in tank_temps]
        iter_count = 0
        while (sorted(layer_temps, reverse=True) != layer_temps and iter_count<20):
            iter_count += 1
            layer_temps = []
            for layer in tank_temps:
                if layer_temps:
                    if tank_temps[layer] > layer_temps[-1]:
                        mean = round((layer_temps[-1] + tank_temps[layer]) / 2)
                        layer_temps[-1] = mean
                        layer_temps.append(mean)
                    else:
                        layer_temps.append(tank_temps[layer])
                else:
                    layer_temps.append(tank_temps[layer])
            for i, layer in enumerate(tank_temps):
                tank_temps[layer] = layer_temps[i]
            if iter_count == 20:
                layer_temps = sorted(layer_temps, reverse=True)

        # Cluster 10 times and select the result with the highest top temperature
        data = layer_temps.copy()
        clustering_runs = []
        for i in range(10):
            labels = await self.kmeans(data, k=3)
            cluster_0 = sorted([data[i] for i in range(len(data)) if labels[i] == 0], reverse=True)
            cluster_1 = sorted([data[i] for i in range(len(data)) if labels[i] == 1], reverse=True)
            cluster_2 = sorted([data[i] for i in range(len(data)) if labels[i] == 2], reverse=True)
            cluster_top = max(cluster_0, cluster_1, cluster_2, key=lambda x: np.mean(x) if len(x)>0 else 0)
            top_temp = sum(cluster_top)/len(cluster_top)
            clustering_runs.append({
                'cluster_0': cluster_0,
                'cluster_1': cluster_1,
                'cluster_2': cluster_2,
                'top_temp': top_temp
            })
        best_run = max(clustering_runs, key=lambda x: x['top_temp'])
        cluster_0 = best_run['cluster_0']
        cluster_1 = best_run['cluster_1']
        cluster_2 = best_run['cluster_2']

        # Dealing with 3 clusters
        if cluster_0 and cluster_1 and cluster_2:
            cluster_top = max(cluster_0, cluster_1, cluster_2, key=lambda x: sum(x)/len(x))
            cluster_bottom = min(cluster_0, cluster_1, cluster_2, key=lambda x: sum(x)/len(x))
            cluster_middle = [
                cluster_x for cluster_x in [cluster_0, cluster_1, cluster_2]
                if cluster_x != cluster_top
                and cluster_x != cluster_bottom
                ][0]

            thermocline1 = max(1, len(cluster_top))
            thermocline2 = thermocline1 + len(cluster_middle)

            top_temp = round(sum(cluster_top)/len(cluster_top))
            middle_temp = round(sum(cluster_middle)/len(cluster_middle))
            bottom_temp = round(sum(cluster_bottom)/len(cluster_bottom))
            self.log(f"Storage model: {top_temp}({thermocline1}){middle_temp}({thermocline2}){bottom_temp} ({len(layer_temps)} layers)")
            return top_temp, middle_temp, bottom_temp, thermocline1, thermocline2

        # Dealing with less than 3 clusters
        else:
            if cluster_0 and cluster_2:
                cluster_1 = cluster_2
            elif cluster_1 and cluster_2:
                cluster_0 = cluster_2
            # Two clusters
            if cluster_0 and cluster_1:
                cluster_top = max(cluster_0, cluster_1, key=lambda x: sum(x)/len(x))
                cluster_bottom = min(cluster_0, cluster_1, key=lambda x: sum(x)/len(x))
                thermocline1 = len(cluster_top)
                top_temp = round(sum(cluster_top)/len(cluster_top))
                bottom_temp = round(sum(cluster_bottom)/len(cluster_bottom))
                self.log(f"Storage model: {top_temp}({thermocline1}){bottom_temp} ({len(layer_temps)} layers)")
                return top_temp, top_temp, bottom_temp, thermocline1, thermocline1
            # Single cluster
            else:
                cluster_top = max(cluster_0, cluster_1, cluster_2, key=lambda x: len(x))
                top_temp = round(sum(cluster_top)/len(cluster_top))
                thermocline1 = len(layer_temps)
                self.log(f"Storage model: {top_temp}({thermocline1}) ({len(layer_temps)} layers)")
                return top_temp, top_temp, top_temp, thermocline1, thermocline1
    
    async def get_buffer_available_kwh(self):
        if self.keep_buffer_full:
            return 0
        if self.seasonal_storage_mode == SeasonalStorageMode.BufferOnly:
            return 0
        if self.tank_temp_channel_names is None:
            self.send_layout()
            await asyncio.sleep(5)
        self.get_latest_temperatures()
        buffer_temperatures: Dict[str, float] = {
            k: v
            for k,v in self.latest_temps_f.items() 
            if 'buffer' in k and v is not None
        }
        self.log(f"Buffer temperatures: {buffer_temperatures}")
        if not buffer_temperatures:
            self.log("Missing temperatures in get_buffer_available_kwh, returning 0 kWh")
            return 0
        try:
            rswt = await self.get_RSWT(minus_deltaT=False)
            rswt_minus_deltaT = await self.get_RSWT(minus_deltaT=True)
            m_layer_kg = 120/4 * 3.785
            buffer_available_energy = 0
            for bl in buffer_temperatures:
                if buffer_temperatures[bl] >= rswt_minus_deltaT:
                    buffer_available_energy += m_layer_kg * 4.187/3600 * (buffer_temperatures[bl]-rswt_minus_deltaT) * 5/9
            if round(buffer_available_energy,2) == 0:
                for bl in buffer_temperatures:
                    buffer_available_energy += - m_layer_kg * 4.187/3600 * (rswt - buffer_temperatures[bl]) * 5/9
            self.log(f"Buffer available kWh: {round(buffer_available_energy,2)}")
            return round(buffer_available_energy,2)
        except Exception as e:
            self.log(f"Something failed in get_buffer_available_kwh ({e}), returning 0 kWh")
            return 0
        
    async def get_house_available_kwh(self):
        setpoints = {}
        temps = {}
        thermal_mass = {}
        zone_names = []
        for zone_setpoint in [x for x in self.latest_channel_values if 'zone' in x and 'set' in x]:
            zone_name = zone_setpoint.replace('-set','')
            zone_names.append(zone_name)
            # Get setpoints for each zone
            if self.latest_channel_values[zone_setpoint] is not None:
                setpoints[zone_name] = round(self.latest_channel_values[zone_setpoint]/1000,1)
            # Get temperatures for each zone
            zone_temp = zone_setpoint.replace('-set','-temp')
            if (zone_temp in self.latest_channel_values and self.latest_channel_values[zone_temp] is not None):
                temps[zone_name] = round(self.latest_channel_values[zone_temp]/1000,1)
            # Get thermal mass for each zone
            zone_name_no_prefix = zone_name[6:] if zone_name[:4]=='zone' else zone_name
            if zone_name_no_prefix in self.layout.zone_list:
                zone_index = self.layout.zone_list.index(zone_name_no_prefix)
                thermal_mass[zone_name] = self.layout.zone_kwh_per_deg_f_list[zone_index]

        self.log(f"Found all zone setpoints: {setpoints}")
        self.log(f"Found all zone temperatures: {temps}")
        self.log(f"Found all zone thermal masses: {thermal_mass}")
        house_availale_kwh = 0
        for zone in zone_names:
            if 'zone4' in zone or 'upstairs' in zone:
                continue
            if zone in temps and zone in setpoints and zone in thermal_mass:
                house_availale_kwh += thermal_mass[zone] * (temps[zone] - setpoints[zone])
        house_availale_kwh = round(house_availale_kwh,2)
        self.log(f"House available kWh: {house_availale_kwh}")
        return min(0, house_availale_kwh) # TODO: TEMPORARY only consider negative values

    async def get_weather(self, session: aiohttp.ClientSession) -> None:
        """The forecast pair from the app's weather source."""
        self.weather_forecast = await self.app.weather_source.forecast(session)

    async def get_price_forecast(self) -> None:
        '''Updates self.price_forecast for the start of next hour. All in USD/MWh'''
        try:
            # Get price forecast from the price service API
            url = "https://price-service.electricity.works/hw1-isone-me-versant-keene-ps/gw0-price-forecast"
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    self.log("Successfully received price forecast from the price service API")
                    data = response.json()
                    self.price_forecast = PriceForecast(
                        dp_usd_per_mwh=data['DistList'],
                        lmp_usd_per_mwh=data['LmpList'],  
                    )
                    # self.log(f"- LMP USD/MWh {self.price_forecast.lmp_usd_per_mwh}")
                    # self.log(f"- Total energy USD/MWh {[round(x,2) for x in self.price_forecast.total_energy]}")
                    
                    # Save price forecast to a local CSV file
                    prices_file = Path(f"{self.settings.paths.data_dir}/price_forecast.csv")
                    # Check if current hour's data exists in the existing file
                    current_hour_row = None
                    if prices_file.exists():
                        current_hour_timestamp = data['HourStartS'][0] - 3600
                        with open(prices_file, 'r', newline='') as f:
                            reader = csv.reader(f)
                            next(reader)  # skip the header row
                            for row in reader:
                                if float(row[0]) == current_hour_timestamp:
                                    current_hour_row = row
                                    break
                    # Write the new file
                    with open(prices_file, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['HourStartS', 'DistList', 'LmpList'])
                        if current_hour_row:
                            writer.writerow(current_hour_row)
                        for i in range(len(data['DistList'])):
                            writer.writerow([data['HourStartS'][i], data['DistList'][i], data['LmpList'][i]])                   
                    self.log(f"Saved price forecast to {prices_file}")
                else:
                    raise Exception(f"Failed to receive price forecast from API, status code: {response.status_code}")
        
        except Exception as e:
            self.log(f"FAILED to receive price forecast from the price service API and/or to save it to a local CSV: {e}")
            self.log("Trying to read price forecast from the local CSV file")
            try:
                # Read the local CSV file with the latest received price forecast
                file_path = Path(f"{self.settings.paths.data_dir}/price_forecast.csv")
                with open(file_path, mode='r', newline='') as file:
                    reader = csv.reader(file)
                    next(reader)
                    rows = list(reader)
                timestamps = [float(row[0]) for row in rows]
                dist_usd_mwh = [float(row[1]) for row in rows]
                lmp_usd_mwh = [float(row[2]) for row in rows]

                self.price_forecast = price_forecast_from(
                    timestamps, dist_usd_mwh, lmp_usd_mwh, self.plant_clock.now()
                )
                self.log("Successfully read price forecast from local CSV.")
                # self.log(f"- LMP USD/MWh {self.price_forecast.lmp_usd_per_mwh}")
                # self.log(f"- Total energy USD/MWh {[round(x,2) for x in self.price_forecast.total_energy]}")

            except Exception as e:
                self.log(f"Could not get a price forecast from the local CSV file: {e}.")
                await self.send_glitch(f"Failed to read price forecast from local CSV file: {e}", log_level=LogLevel.Error)

    async def send_glitch(self, summary, details="", log_level=LogLevel.Info):
        glitch = Glitch(
            FromGNodeAlias=self.g_node_alias,
            Node=self.node.name,
            Type=log_level,
            Summary=summary,
            Details=details,
            CreatedMs=self.plant_clock.now_ms()
        )
        self.services.send_threadsafe(Message(Src=self.name, Dst=self.name, Payload=glitch))
        self.log("Sent glitch")

    def log(self, note: str) -> None:
        log_str = f"[ltn] {note}"
        self.services.logger.error(log_str)

    def dbg(
        self,
        message_summary: int = -1,
        lifecycle: int = -1,
        comm_event: int = -1,
        command: Optional[DBGCommands | str] = None,
    ):
        self.send_dbg_to_peer(
            message_summary=message_summary,
            lifecycle=lifecycle,
            comm_event=comm_event,
            command=command,
        )

    def send_dbg_to_peer(
        self,
        message_summary: int = -1,
        lifecycle: int = -1,
        comm_event: int = -1,
        command: Optional[DBGCommands | str] = None,
    ):
        if isinstance(command, str):
            command = DBGCommands(command)
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=DBGPayload(
                    Levels=LoggerLevels(
                        message_summary=message_summary,
                        lifecycle=lifecycle,
                        comm_event=comm_event,
                    ),
                    Command=command,
                ),
            )
        )

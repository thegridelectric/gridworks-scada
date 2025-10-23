"""Scada implementation"""
import csv
import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Dict, List, Optional, Tuple, cast, Callable
from typing import Sequence

import numpy as np
import pytz
import aiohttp
import random
import rich
import httpx
from gwproactor import CodecFactory
from gwproactor import LinkSettings
from gwproactor import PrimeActor
from gwproactor import ProactorLogger
from gwproactor import ProactorName
from gwproactor import AppInterface
from gwproto import HardwareLayout

from actors.flo import DGraph
from gwsproto.data_classes.house_0_layout import House0Layout
from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import MarketPriceUnit, MarketQuantityUnit, MarketTypeName, HomeAloneStrategy
from gwsproto.data_classes.house_0_names import House0RelayIdx
from gwproactor import QOS
from gwproactor.config import LoggerLevels
from gwproactor.logger import LoggerOrAdapter
from gwproactor.message import DBGCommands, DBGPayload, MQTTReceiptPayload
from gwproto import Message, MQTTCodec, create_message_model
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import TelemetryName, RelayClosedOrOpen
from gwproto.messages import (EventBase, PowerWatts, Report, ReportEvent)
from gwproto.named_types import AnalogDispatch, SendSnap, MachineStates
from actors.atn_contract_handler import AtnContractHandler
from gwsproto.enums import ContractStatus, LogLevel
from gwsproto.named_types import (
    AtnBid, FloParamsHouse0, Glitch, Ha1Params, LatestPrice, LayoutLite, NoNewContractWarning,
    ResetHpKeepValue, ScadaParams, SendLayout, SetLwtControlParams, SiegLoopEndpointValveAdjustment,
    SlowContractHeartbeat,  SnapshotSpaceheat, StartListeningToAtn, StopListeningToAtn
)

from paho.mqtt.client import MQTTMessageInfo
from pydantic import BaseModel

from actors.atn.atn_config import AtnSettings, DashboardSettings
from actors.atn.dashboard.dashboard import Dashboard

TANK_GALLONS = 120
class PriceForecast(BaseModel):
    dp_usd_per_mwh: List[float]
    lmp_usd_per_mwh: List[float]
    reg_usd_per_mwh: List[float]

    @property
    def total_energy(self) -> List[float]:
        """Calculate the total price forecast by summing dp, lmp, and reg components."""
        return [dp + lmp for dp, lmp in zip(self.dp_usd_per_mwh, self.lmp_usd_per_mwh)]


class BidRunner(threading.Thread):
    def __init__(self, params: FloParamsHouse0,
                 atn_settings: AtnSettings,
                 atn_name: str, 
                 atn_g_node_alias: str,
                 send_threadsafe: Callable[[Message], None],
                 on_complete: Callable[[str], None],
                 logger: LoggerOrAdapter):
        super().__init__()
        self.stop_event = threading.Event()
        self.logger = logger or print  # Fallback to print if no logger provided
        self.params = params
        self.atn_settings = atn_settings
        self.atn_name = atn_name
        self.atn_alias = atn_g_node_alias
        self.send_threadsafe = send_threadsafe
        self.on_complete = on_complete
        self.bid: Optional[AtnBid] = None
        self.get_bid_event = threading.Event()

    def run(self):
        try:
            while not self.stop_event.is_set():
                # Run FLO
                self.logger.info("Creating graph and solving Dijkstra...")
                st = time.time()
                g = DGraph(self.params, self.logger)
                g.solve_dijkstra()
                self.logger.info(f"Built and solved in {round(time.time()-st,2)} seconds!")
                # After solving, trim the graph to reduce memory usage while waiting
                g.trim_graph_for_waiting()
                # Pause until get_bid is called
                self.get_bid_event.clear()
                self.logger.info("BidRunner waiting for get_bid to be called before computing bid.")
                self.get_bid_event.wait()

                self.logger.info("Generating bid...")
                g.generate_bid(self.updated_flo_params)
                self.logger.info(f"Done! Found {len(g.pq_pairs)} PQ pairs.")

                # Generate bid
                t = time.time()
                slot_start_s = int(t - (t % 3600)) + 3600
                mtn = MarketTypeName.rt60gate5.value
                market_slot_name = f"e.{mtn}.{Atn.P_NODE}.{slot_start_s}"
                self.bid = AtnBid(
                    BidderAlias=self.atn_alias,
                    MarketSlotName=market_slot_name,
                    PqPairs=g.pq_pairs,
                    InjectionIsPositive=False,  # withdrawing energy since load not generation
                    PriceUnit=MarketPriceUnit.USDPerMWh,
                    QuantityUnit=MarketQuantityUnit.AvgkW,
                    SignedMarketFeeTxn="BogusAlgoSignature",
                )
                
                # Send bid through ATN's message processing
                self.send_threadsafe(
                    Message(
                        Src=self.atn_name,
                        Dst=self.atn_name,
                        Payload=self.bid
                    )
                )

                # Explicitly delete the graph to free memory
                del g

                break
        except Exception as e:
            self.logger.info(f"An error occured running Dijkstra or getting bid: {e}")
        finally:
            # Ensure cleanup happens even if there's an error
            self.logger.info("Done running bid runner")
            self.on_complete(self.atn_name)

    def get_bid(self, updated_flo_params: FloParamsHouse0):
        self.logger.info("Getting bid...")
        self.updated_flo_params = updated_flo_params
        self.get_bid_event.set()

    def stop(self):
        self.logger.info("Stopping BidRunner")
        self.stop_event.set()


class AtnMQTTCodec(MQTTCodec):
    exp_src: str
    exp_dst: str = H0N.atn

    def __init__(self, hardware_layout: House0Layout):
        self.exp_src = hardware_layout.scada_g_node_alias
        super().__init__(
            create_message_model(
                model_name="AtnMessageDecoder",
                module_names=[
                    "gwsproto.named_types",
                    "gwproto.messages",
                    "gwproactor.message",
                ],
            )
        )

    def validate_source_and_destination(self, src: str, dst: str) -> None:
        if src != self.exp_src or dst != self.exp_dst:
            raise ValueError(
                "ERROR validating src and/or dst\n"
                f"  exp: {self.exp_src} -> {self.exp_dst}\n"
                f"  got: {src} -> {dst}"
            )

class AtnCodecFactory(CodecFactory):
    def get_codec(
        self,
        link_name: str,
        link: LinkSettings,
        proactor_name: ProactorName,
        layout: HardwareLayout,
    ) -> MQTTCodec:
        if not isinstance(layout, House0Layout):
            raise ValueError(
                "ERROR. ScadaCodecFactory requires hardware layout "
                "to be an instance of House0Layout but received layout type "
                f"<{type(layout)}>"
            )
        return AtnMQTTCodec(layout)


class Telemetry(BaseModel):
    Value: int
    Unit: TelemetryName


@dataclass
class AtnData:
    layout: House0Layout
    my_channels: List[DataChannel]
    latest_snapshot: Optional[SnapshotSpaceheat] = None
    latest_report: Optional[Report] = None
    latest_power_w: Optional[int] = None

    def __init__(self, layout: House0Layout):
        self.layout = layout
        self.my_channels = list(layout.data_channels.values())
        self.latest_snapshot = None
        self.latest_report = None
        self.latest_power_w = None

    
class Atn(PrimeActor):
    MAIN_LOOP_SLEEP_SECONDS = 61
    HEARTBEAT_INTERVAL_S = 60
    P_NODE = "hw1.isone.ver.keene"
    SCADA_MQTT = "scada_mqtt"
    data: AtnData
    event_loop_thread: Optional[threading.Thread] = None
    bid_runner: Optional[threading.Thread]
    dashboard: Optional[Dashboard]
    ha1_params: Optional[Ha1Params]
    _stop_requested: bool = False


    def __init__(self, name: str, services: AppInterface) -> None:
        super().__init__(name, services)
        # self._web_manager.disable()
        self.data = AtnData(self.layout)
        self.is_simulated = self.settings.is_simulated
        self.latest_channel_values: Dict[str, int] = {}
        self.timezone = pytz.timezone(self.settings.timezone_str)
        self.latitude = self.settings.latitude
        self.longitude = self.settings.longitude
        self.sent_bid = False
        self.flo_params = None
        self.hp_is_off = False
        self.weather_forecast = None
        self.coldest_oat_by_month = [-3, -7, 1, 21, 30, 31, 46, 47, 28, 24, 16, 0]
        self.price_forecast: Optional[PriceForecast] = None
        self.data_channels: List
        self.temperature_channel_names = None
        self.ha1_params: Optional[Ha1Params] = None
        self.latest_report: Optional[Report] = None
        self.report_output_dir = Path(f"{self.settings.paths.data_dir}/report")
        self.report_output_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.dashboard.print_gui:
            self.dashboard = Dashboard(
                settings=self.settings.dashboard,
                atn_g_node_alias=self.layout.atn_g_node_alias,
                data_channels=self.layout.data_channels,
                thermostat_names=DashboardSettings.thermostat_names(
                    [channel.Name for channel in self.layout.data_channels.values()]
                ),
                logger=self.logger,
            )
        else:
            self.dashboard = None
        self.next_contract_energy_wh: Optional[int] = None
        self.contract_handler: AtnContractHandler = AtnContractHandler(
            node=self.node,
            settings=self.settings,
            layout=self.layout,
            logger=self.logger.add_category_logger(
                AtnContractHandler.LOGGER_NAME,
                level=self.settings.contract_rep_logging_level
            ),
            send_threadsafe=self.services.send_threadsafe,
        )
        self.bid_runner: Optional[BidRunner] = None
        self.sending_contracts: bool = True
        self.send_bid_minute: int = 57
        min_minute = min(max(3, datetime.now().minute), self.send_bid_minute-2)
        self.create_graph_minute: int = random.randint(min_minute, self.send_bid_minute-1)
        # Gets strategy from scada sending LayoutLite
        self.layout_lite: Optional[LayoutLite] = None # Add this as a way of tracking if we've gotten the layout lite yet
        self.strategy = HomeAloneStrategy.default() # will get updated when LayoutLite arrives from Scada
        self.total_store_tanks = 3 # will also get updated when LayoutLite arrives

    @classmethod
    def get_codec_factory(cls) -> AtnCodecFactory:
        return AtnCodecFactory()

    @property
    def logger(self) -> ProactorLogger:
        return self.services.logger

    @property
    def name(self) -> str:
        return self._name

    @cached_property
    def short_name(self) -> str:
        return self.services.subscription_name

    @property
    def node(self) -> ShNode:
        return self._node

    @property
    def scada(self) -> ShNode:
        return self.layout.node(H0N.primary_scada)

    @property
    def publication_name(self) -> str:
        return self.services.publication_name

    @property
    def subscription_name(self) -> str:
        return self.services.subscription_name

    @property
    def settings(self) -> AtnSettings:
        return cast(AtnSettings, self.services.settings)

    @property
    def layout(self) -> House0Layout:
        return cast(House0Layout, self.services.hardware_layout)

    def _publish_to_scada(self, payload, qos: QOS = QOS.AtMostOnce) -> MQTTMessageInfo:
        return self.services.publish_message(
            Atn.SCADA_MQTT, Message(Src=self.publication_name, Payload=payload), qos=qos
        )

    def process_internal_message(self, message: Message):
        path_dbg = 0
        self.logger.path(
            "++Atn.process_internal_message %s/%s",
            message.Header.Src,
            message.Header.MessageType,
        )
        if message.Header.Dst == self.scada.name:
            path_dbg |= 0x00000001
            self._publish_to_scada(message.Payload)
        else:
            path_dbg |= 0x00000002
            self.process_atn_message(message)
        self.logger.path("--Atn.process_internal_message  path:0x%08X",path_dbg)


    def process_atn_message(self, message: Message):
        self.logger.path(
            "++Atn.process_atn_message %s/%s",
            message.Header.Src,
            message.Header.MessageType,
        )
        path_dbg = 0
        match message.Payload:
            case AtnBid():
                path_dbg |= 0x00000001
                bid = message.Payload
                self.contract_handler.latest_bid = bid
                self.services.publish_message(
                    self.SCADA_MQTT, 
                    Message(Src=self.publication_name, Dst="broadcast", Payload=bid)
                )  
                self.log(f"Bid: {bid}")
                self.sent_bid = True
            case Glitch():
                path_dbg |= 0x00000002
                self.services.publish_message(
                    self.SCADA_MQTT,
                    Message(Src=self.publication_name, Dst="broadcast", Payload=message.Payload)
                )
            case LatestPrice():
                path_dbg |= 0x00000004
                self.process_latest_price(message.Payload)
                # self._publish_to_scada(message.Payload) # so we can record in database
            case _:
                path_dbg |= 0x00000008
        self.logger.path("--Atn._derived_process_message  path:0x%08X", path_dbg)

    def process_mqtt_message(
        self, message: Message[MQTTReceiptPayload], decoded: Any
    ):
        self.logger.path(
            "++Atn.process_mqtt_message %s", message.Payload.message.topic
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
            case NoNewContractWarning():
                path_dbg |= 0x00000002
                self.process_no_new_contract_warning(decoded.Payload)
            case PowerWatts():
                path_dbg |= 0x00000004
                self.process_power_watts(decoded.Payload)
            case Report():
                path_dbg |= 0x00000008
                self.process_report(decoded.Payload)
            case ScadaParams():
                path_dbg |= 0x00000010
                self.process_scada_params(decoded.Payload)
            case SnapshotSpaceheat():
                path_dbg |= 0x00000020
                self.process_snapshot(decoded.Payload)
            case SlowContractHeartbeat():
                self.contract_handler.process_slow_contract_heartbeat(decoded.Payload)
            case StartListeningToAtn():
                self.start_sending_contracts()
            case StopListeningToAtn():
                # TODO: break current active contract as well
                self.stop_sending_contracts()
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
        self.logger.path("--Atn.process_mqtt_message  path:0x%08X", path_dbg)

    def process_no_new_contract_warning(self, payload: NoNewContractWarning) -> None:
        """
        Resending a "Created" hb if it exists
        """
        hb = self.contract_handler.latest_hb
        if hb:
            if hb.Status == ContractStatus.Created:
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
            telemetry_name = channel.TelemetryName
            if (
                telemetry_name == TelemetryName.WaterTempCTimes1000
                or telemetry_name == TelemetryName.WaterTempCTimes1000.value
            ):
                centigrade = single_reading.Value / 1000
                if self.settings.c_to_f:
                    fahrenheit = (centigrade * 9 / 5) + 32
                    extra = f"{fahrenheit:5.2f} F"
                else:
                    extra = f"{centigrade:5.2f} C"
            else:
                extra = f"{single_reading.Value} " f"{telemetry_name}"
            s += f"  {channel.AboutNodeName}: {extra}\n"
        return s

    def process_scada_params(self, params: ScadaParams) -> None:
        if params.NewParams:
            print(f"Old: {self.ha1_params}")
            print(f"New: {params.NewParams}")
            self.ha1_params = params.NewParams

    def process_snapshot(self, snapshot: SnapshotSpaceheat) -> None:
        self.data.latest_snapshot = snapshot

        if self.settings.dashboard.print_gui and self.dashboard:
            self.dashboard.process_snapshot(snapshot)
        if self.settings.dashboard.print_snap:
            self.logger.warning(self.snapshot_str(snapshot))
        for reading in snapshot.LatestReadingList:
            self.latest_channel_values[reading.ChannelName] = reading.Value
        if self.is_simulated and self.temperature_channel_names is not None:
            for channel in self.temperature_channel_names:
                self.latest_channel_values[channel] = 60000

    def process_layout_lite(self, layout: LayoutLite) -> None:
        """ ContractState: Initializing -> Ready if needed
        """
        self.log(f"Processing layout lite")
        self.logger.info(f"Processing layout lite: {layout}")
        self.layout_lite = layout
        self.ha1_params = layout.Ha1Params
        try:
            home_alone_strategy = getattr(self.layout.node(H0N.home_alone), "Strategy", None)
            self.strategy = HomeAloneStrategy(home_alone_strategy)
            if home_alone_strategy is None:
                raise ValueError(f"Could not read HomeAlone strategy from layout.")
        except ValueError as e:
            self.log(f"Error getting HomeAlone strategy: {e}")
            self.strategy = HomeAloneStrategy.default()
        self.total_store_tanks = layout.TotalStoreTanks
        self.log(f"FLO strategy: {self.strategy}")

        self.temperature_channel_names = [
            x.Name
            for x in layout.DataChannels
            if "depth" in x.Name and "micro-v" not in x.Name
        ]
        if self.contract_handler.layout_received is False:
            self.contract_handler.layout_received = True # Necessary for bids & contracts
            self.log("Received layout data - ATN now ready for contract operations")

    def process_report(self, report: Report) -> None:
        self.data.latest_report = report
        # Check if HP is on or off by looking at relay 6
        for machine_state in report.StateList:
            ms : MachineStates = machine_state
            if f"relay{House0RelayIdx.hp_scada_ops}" in ms.MachineHandle:
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
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                ),
            )
        )

    def send_new_params(self, new: Ha1Params) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=ScadaParams(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromName=H0N.atn,
                    ToName=H0N.home_alone,
                    UnixTimeMs=int(time.time() * 1000),
                    MessageId=str(uuid.uuid4()),
                    NewParams=new,
                ),
            )
        )

    def send_layout(self) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SendLayout(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromName=H0N.atn,
                    ToName=H0N.primary_scada,
                ),
            )
        )
        self.log("Requesting layout")

    def stop_sending_contracts(self) -> None:
        self.sending_contracts = False
        self.log("Stop sending contracts")

    def start_sending_contracts(self) -> None:
        self.sending_contracts = True
        self.log("Start sending contracts")

    def start_tasks(self) -> Sequence[asyncio.Task[Any]]:
        return  [
            asyncio.create_task(self.main(), name="atn-main"),
            asyncio.create_task(
                self.contract_handler.contract_heartbeat_task(),
                name="contract_heartbeat"
            ),
            asyncio.create_task(self.fake_market_maker(), name="fake market maker")
        ]

    async def main(self):
        async with aiohttp.ClientSession() as session:
            await self.main_loop(session)

    async def main_loop(self, session: aiohttp.ClientSession) -> None:
        await asyncio.sleep(5)
        self.send_layout()

        while not self._stop_requested:
            if not self.settings.monitor_only:
                if datetime.now().minute >= self.create_graph_minute:
                    if not self.flo_params and not self.bid_runner:
                        try:
                            await self.run_d(session)
                        except Exception as e:
                            self.log(f"Exception running Dijkstra: {e}")
                    elif self.flo_params and self.bid_runner:
                        if datetime.now().minute >= self.send_bid_minute and not self.sent_bid:
                            self.log("Finding current storage state...")
                            result = await self.get_three_layer_storage_model()
                            if result is None:
                                self.log("get_three_layer_storage_model() failed! Not getting bid.")
                            else:
                                t, m, b, th1, th2 = result
                                self.flo_params.InitialTopTempF = int(t)
                                self.flo_params.InitialMiddleTempF = int(m)
                                self.flo_params.InitialBottomTempF = int(b)
                                self.flo_params.InitialThermocline1 = int(th1*2)
                                self.flo_params.InitialThermocline2 = int(th2*2)
                                self.services.publish_message(
                                    self.SCADA_MQTT,
                                    Message(Src=self.publication_name, Dst="broadcast", Payload=self.flo_params)
                                )
                                self.bid_runner.get_bid(self.flo_params)
                        elif not self.sent_bid:
                            self.log(f"Graph was already created. Waiting for minute {self.send_bid_minute} to send bid.")
                        elif self.sent_bid:
                            self.log("Already sent bid.")
                else:
                    if self.flo_params:
                        self.flo_params = None
                        self.sent_bid = False
                    else:
                        self.log(f"No graph exists. Waiting for minute {self.create_graph_minute} to create graph.")

                # TODO: not sure what this is for
                if not ((datetime.now().minute >= self.create_graph_minute and not self.flo_params)
                        or (datetime.now().minute <= self.create_graph_minute and self.flo_params)):
                    if self.contract_handler.latest_hb is None:
                        self.log("No active contract.")

            await asyncio.sleep(self.MAIN_LOOP_SLEEP_SECONDS)

    async def run_d(self, session: aiohttp.ClientSession) -> None:
        """Prepare parameters and start a bid computation.
    
        This method is async because it needs to fetch weather forecasts,
        but the actual Dijkstra computation runs in a separate thread.
        Async parallelizes waiting (like HTTP requests) but does not 
        gracefully handle high CPU use. The additional thread handles
        the CPU-intensive graph computation.
        """
        if self.flo_params:
            self.log("NOT RUNNING Dijsktra! Already created graph")
            return
        
        # Check if there's already a bid runner
        if self.bid_runner and self.bid_runner.is_alive():
            self.log("BidRunner already running!")
            return

        if datetime.now().minute >= self.create_graph_minute:
            dijkstra_start_time = int(
                datetime.timestamp((datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0))
                )
        else:
            dijkstra_start_time = int(datetime.timestamp(datetime.now()))
            self.log(f"NOT RUNNING Dijkstra! Not past minute {self.create_graph_minute}")
            return
        await self.get_weather(session)
        await self.get_price_forecast_48h()

        if not self.layout_lite:
            self.log("Do not have layout lite from scada so not running dijkstra... must not be connected!!")
            return

        if self.strategy == HomeAloneStrategy.Summer:
            self.log("Should not be running FLOs when Scada is in Summer!! Sent glitch")
            glitch = Glitch(
                FromGNodeAlias=self.layout.atn_g_node_alias,
                Node=self.node.name,
                Type=LogLevel.Warning,
                Summary="Should not be running FLOs when Scada is in Summer!!",
                Details="",
                CreatedMs=int(time.time() * 1000)
            )
            self.services.send_threadsafe(
                Message(Src=self.name, Dst=self.name, Payload=glitch))
            return

        self.log("Finding thermocline position and top temperature")
        result = await self.get_three_layer_storage_model()
        if self.strategy == HomeAloneStrategy.ShoulderTou:
            self.log(f"Buffer model: {result}")
        else:
            self.log(f"Storage model: {result}")
        if result is None:
            self.log("Get thermocline and centroid failed! Not running FLO!")
            return
        t, m, b, th1, th2 = result

        buffer_available_kwh = await self.get_buffer_available_kwh()
        house_available_kwh = await self.get_house_available_kwh()
        if self.price_forecast is None:
            self.log("Not running flo - no price forecast")
            return
        if self.weather_forecast is None:
            self.log("Not running flo - no weather forecast")
            return
        if self.ha1_params is None:
            self.log("Not running flo - no ha1_params")
            return
        self.flo_params = FloParamsHouse0(
            GNodeAlias=self.layout.scada_g_node_alias,
            StartUnixS=dijkstra_start_time,
            InitialTopTempF=int(t),
            InitialMiddleTempF=int(m),
            InitialBottomTempF=int(b),
            InitialThermocline1= int(th1*2),
            InitialThermocline2= int(th2*2),
            StorageVolumeGallons = TANK_GALLONS if self.strategy == HomeAloneStrategy.ShoulderTou else self.total_store_tanks * TANK_GALLONS,
            # TODO: price and weather forecasts should include the current hour if we are running a partial hour
            LmpForecast=self.price_forecast.lmp_usd_per_mwh,
            DistPriceForecast=self.price_forecast.dp_usd_per_mwh,
            RegPriceForecast=self.price_forecast.reg_usd_per_mwh,
            OatForecastF=self.weather_forecast["oat"],
            WindSpeedForecastMph=self.weather_forecast["ws"],
            AlphaTimes10=self.ha1_params.AlphaTimes10,
            BetaTimes100=self.ha1_params.BetaTimes100,
            GammaEx6=self.ha1_params.GammaEx6,
            IntermediatePowerKw=self.ha1_params.IntermediatePowerKw,
            IntermediateRswtF=self.ha1_params.IntermediateRswtF,
            DdPowerKw=self.ha1_params.DdPowerKw,
            DdRswtF=self.ha1_params.DdRswtF,
            DdDeltaTF=self.ha1_params.DdDeltaTF,
            MaxEwtF=self.ha1_params.MaxEwtF,
            HpIsOff=self.hp_is_off,
            BufferAvailableKwh=buffer_available_kwh,
            HouseAvailableKwh=house_available_kwh
        )
        self.services.publish_message(
            self.SCADA_MQTT, 
            Message(Src=self.publication_name, Dst="broadcast", Payload=self.flo_params)
        )
        self.bid_runner = BidRunner(
            params=self.flo_params,
            atn_settings=self.settings,
            atn_name=self.name, 
            atn_g_node_alias=self.layout.atn_g_node_alias,
            send_threadsafe=self.services.send_threadsafe,
            on_complete=self._cleanup_bid_runner,
            logger=self.logger.add_category_logger(
                DGraph.LOGGER_NAME,
                level=self.settings.flo_logging_level
            ),
        )
        self.bid_runner.start()  
        # Instead of waiting, return to event loop
        self.log("Started Dijkstra computation in background")

    def _cleanup_bid_runner(self, atn_name: str) -> None:
        """Callback to clean up bid runner when it's done.
        Note: This is called from the BidRunner thread."""
        self.log("Cleaned up bid runner")
        self.bid_runner = None

    def latest_contract_is_live(self) -> bool:
        """ Validates that the bid's market slot name corresponds to the current hour."""
        bid = self.contract_handler.latest_bid
        if not bid:
            return False
            
        # Extract slot start time from market slot name
        try:
            market_slot_name_parts = bid.MarketSlotName.split('.')
            slot_start_s = int(market_slot_name_parts[-1])
            
            # Get current hour start in unix time
            now = time.time()
            current_hour_start_s = int(now - (now % 3600))
            
            # Check if bid is for current hour
            if slot_start_s != current_hour_start_s:
                self.log(f"Bid time mismatch: bid for {slot_start_s}, current hour starts at {current_hour_start_s}")
                
                return False
                
            return True
        except (ValueError, IndexError) as e:
            self.log(f"Error validating bid time: {e}")
            return False

    def process_latest_price(self, payload: LatestPrice) -> None:
        if not self.sending_contracts:
            self.log("Not sending contracts, so ignoring latest price")
            return
        self.contract_handler.latest_price = payload
        self.log("Received latest price")
        if self.contract_handler.latest_bid is None:
            self.log("Ignoring - no bid exists")
            return

        # Validate bid timeframe
        if not self.latest_contract_is_live():
            glitch = Glitch(
                FromGNodeAlias=self.layout.atn_g_node_alias,
                Node=self.node.name,
                Type=LogLevel.Warning,
                Summary="Invalid bid timeframe",
                Details=f"Stale bid detected. Bid slot start: {self.contract_handler.latest_bid.MarketSlotName}. Current price: {payload.MarketSlotName}",
                CreatedMs=int(time.time() * 1000)
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

        pq_pairs = [
            (x.PriceTimes1000, x.QuantityTimes1000) for x in self.contract_handler.latest_bid.PqPairs
        ]
        sorted_pq_pairs = sorted(pq_pairs, key=lambda pair_: pair_[0])
        # Quantity is AvgkW, so QuantityTimes1000 is avg_w
        assert self.contract_handler.latest_bid.QuantityUnit == MarketQuantityUnit.AvgkW
        for pair in sorted_pq_pairs:
            if pair[0] < payload.PriceTimes1000:
                avg_w = pair[1] # WattHours

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

    def to_fahrenheit(self, t: float) -> float:
        return t * 9 / 5 + 32

    def fill_missing_store_temps(self):
        all_store_layers = sorted(
            [x for x in self.temperature_channel_names if "tank" in x]
        )
        for layer in all_store_layers:
            if (
                layer not in self.latest_temperatures
                or self.to_fahrenheit(self.latest_temperatures[layer] / 1000) < 70
                or self.to_fahrenheit(self.latest_temperatures[layer] / 1000) > 200
            ):
                self.latest_temperatures[layer] = None
        if H0CN.store_cold_pipe in self.latest_temperatures:
            value_below = self.latest_temperatures[H0CN.store_cold_pipe]
        else:
            value_below = 0
        for layer in sorted(all_store_layers, reverse=True):
            if self.latest_temperatures[layer] is None:
                self.latest_temperatures[layer] = value_below
            value_below = self.latest_temperatures[layer]
        self.latest_temperatures = {
            k: self.latest_temperatures[k] for k in sorted(self.latest_temperatures)
        }

    def get_latest_temperatures(self):
        if self.temperature_channel_names is None:
            self.temperatures_available = False
            self.log("Can't get latest temperatures, don't have temperature channel names!")
            return
        if not self.settings.is_simulated:
            temp = {
                x: self.latest_channel_values[x]
                for x in self.temperature_channel_names
                if x in self.latest_channel_values
                and self.latest_channel_values[x] is not None
            }
            self.latest_temperatures = temp.copy()
        else:
            self.log("IN SIMULATION - set all temperatures to 60 degC")
            self.latest_temperatures = {}
            for channel_name in self.temperature_channel_names:
                self.latest_temperatures[channel_name] = 60 * 1000
        if list(self.latest_temperatures.keys()) == self.temperature_channel_names:
            self.temperatures_available = True
        else:
            self.temperatures_available = False
            all_buffer = [
                x for x in self.temperature_channel_names if "buffer-depth" in x
            ]
            available_buffer = [
                x for x in list(self.latest_temperatures.keys()) if "buffer-depth" in x
            ]
            if all_buffer == available_buffer:
                self.fill_missing_store_temps()
                self.temperatures_available = True

    async def get_RSWT(self, minus_deltaT=False):
        if self.ha1_params is None:
            raise Exception("ha1_params cannot be None here!")
        if self.weather_forecast is None:
            raise Exception("weather_forecast cannot be None here!")
        try:
            alpha = self.ha1_params.AlphaTimes10 / 10
            beta = self.ha1_params.BetaTimes100 / 100
            gamma = self.ha1_params.GammaEx6 / 1e6
            oat = self.weather_forecast["oat"][0]
            ws = self.weather_forecast["ws"][0]
            r = alpha + beta*oat + gamma*ws
            rhp= r if r>0 else 0
            intermediate_rswt = self.ha1_params.IntermediateRswtF
            dd_rswt = self.ha1_params.DdRswtF
            intermediate_power = self.ha1_params.IntermediatePowerKw
            dd_power = self.ha1_params.DdPowerKw
            no_power_rswt = -alpha/beta
            x_rswt = np.array([no_power_rswt, intermediate_rswt, dd_rswt])
            y_hpower = np.array([0, intermediate_power, dd_power])
            A = np.vstack([x_rswt**2, x_rswt, np.ones_like(x_rswt)]).T
            a, b, c = np.linalg.solve(A, y_hpower)
            c2 = c - rhp
            rswt = round((-b + (b**2-4*a*c2)**0.5)/(2*a),2)
            deltaT = self.ha1_params.DdDeltaTF/self.ha1_params.DdPowerKw * (a*rswt**2 + b*rswt + c)
            deltaT = deltaT if deltaT>0 else 0
            if minus_deltaT:
                return rswt - deltaT
            return rswt
        except:
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

    async def get_three_layer_storage_model(self) -> Optional[Tuple[float, int, int, int, int]]:
        # Get all storage tank temperatures in a dict
        if self.temperature_channel_names is None:
            self.send_layout()
            await asyncio.sleep(5)
        self.get_latest_temperatures()
        if not self.temperatures_available:
            self.log("Not enough tank temperatures available to compute top temperature and thermocline!")
            return None
        all_layers = sorted(
            [x for x in self.temperature_channel_names if ("buffer" if self.strategy == HomeAloneStrategy.ShoulderTou else "tank") in x]
        )
        try:
            tank_temps = {
                key: self.to_fahrenheit(self.latest_temperatures[key] / 1000) 
                for key in all_layers
            }
        except KeyError as e:
            self.log(f"Failed to get all the tank temps in get_three_layer_storage_model! Bailing on process {e}")
            return None

        if self.strategy == HomeAloneStrategy.ShoulderTou:
            top_temp = round(tank_temps[H0CN.buffer.depth1],1)
            middle_temp = round(tank_temps[H0CN.buffer.depth2],1)
            bottom_temp = round(tank_temps[H0CN.buffer.depth3],1)
            thermocline1 = 4 #out of 12 layers
            thermocline2 = 8 #out of 12 layers
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
            self.log(f"Storage model: {top_temp}({thermocline1}){middle_temp}({thermocline2}){bottom_temp}")
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
                self.log(f"Storage model: {top_temp}({thermocline1}){bottom_temp}")
                return top_temp, top_temp, bottom_temp, thermocline1, thermocline1
            # Single cluster
            else:
                cluster_top = max(cluster_0, cluster_1, cluster_2, key=lambda x: len(x))
                top_temp = round(sum(cluster_top)/len(cluster_top))
                thermocline1 = 12
                self.log(f"Storage model: {top_temp}({thermocline1})")
                return top_temp, top_temp, top_temp, thermocline1, thermocline1
    
    async def get_buffer_available_kwh(self):
        if self.strategy == HomeAloneStrategy.ShoulderTou:
            return 0
        if self.temperature_channel_names is None:
            self.send_layout()
            await asyncio.sleep(5)
        self.get_latest_temperatures()
        buffer_temperatures = {k: self.to_fahrenheit(v/1000)
                               for k,v in self.latest_temperatures.items() 
                               if 'buffer' in k
                               and v is not None}
        if not buffer_temperatures:
            self.log("Missing temperatures in get_buffer_available_kwh, returning 0 kWh")
            return 0
        try:
            rswt = await self.get_RSWT(minus_deltaT=False)
            rswt_minus_deltaT = await self.get_RSWT(minus_deltaT=True)
            m_layer_kg = 120/4 * 3.785
            buffer_available_energy = 0
            for bl in buffer_temperatures:
                if buffer_temperatures[bl] >= rswt:
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
        zone_names = []
        for zone_setpoint in [x for x in self.latest_channel_values if 'zone' in x and 'set' in x]:
            zone_name = zone_setpoint.replace('-set','')
            zone_names.append(zone_name)
            if self.latest_channel_values[zone_setpoint] is not None:
                setpoints[zone_name] = round(self.latest_channel_values[zone_setpoint]/1000,1)
            if (zone_setpoint.replace('-set','-temp') in self.latest_channel_values
                and self.latest_channel_values[zone_setpoint.replace('-set','-temp')] is not None):
                temps[zone_name] = round(self.latest_channel_values[zone_setpoint.replace('-set','-temp')]/1000,1)
        self.log(f"Found all zone setpoints: {setpoints}")
        self.log(f"Found all zone temperatures: {temps}")
        thermal_mass_kwh_per_degf = 1
        house_availale_kwh = 0
        for zone in zone_names:
            if zone in temps and zone in setpoints:
                house_availale_kwh += thermal_mass_kwh_per_degf * (temps[zone] - setpoints[zone])
        house_availale_kwh = round(house_availale_kwh,2)
        self.log(f"House available kWh: {house_availale_kwh}")
        return house_availale_kwh

    async def get_weather(self, session: aiohttp.ClientSession) -> None:
        config_dir = self.settings.paths.config_dir
        weather_file = Path(f"{config_dir}/weather.json")
        try:
            url = f"https://api.weather.gov/points/{self.latitude},{self.longitude}"
            response =  await session.get(url)
            if response.status != 200:
                self.log(f"Error fetching weather data: {response.status}")
                return None
            data = await response.json()
            forecast_hourly_url = data["properties"]["forecastHourly"]
            forecast_response = await session.get(forecast_hourly_url)
            if forecast_response.status != 200:
                self.log(
                    f"Error fetching hourly weather forecast: {forecast_response.status}"
                )
                return None
            forecast_data = await forecast_response.json()
            forecasts = {}
            periods = forecast_data["properties"]["periods"]
            for period in periods:
                if (
                    "temperature" in period
                    and "startTime" in period
                    and datetime.fromisoformat(period["startTime"])
                    > datetime.now(tz=self.timezone)
                ):
                    forecasts[datetime.fromisoformat(period["startTime"])] = period[
                        "temperature"
                    ]
            forecasts = dict(list(forecasts.items())[:96])
            cropped_forecast = dict(list(forecasts.items())[:48])
            wf = {
                "time": list(cropped_forecast.keys()),
                "oat": list(cropped_forecast.values()),
                "ws": [0] * len(cropped_forecast),
            }
            self.log(
                f"Obtained a {len(forecasts)}-hour weather forecast starting at {wf['time'][0]}"
            )
            weather_long = {
                "time": [x.timestamp() for x in list(forecasts.keys())],
                "oat": list(forecasts.values()),
                "ws": [0] * len(forecasts),
            }
            with open(weather_file, "w") as f:
                json.dump(weather_long, f, indent=4)

        except Exception as e:
            self.log(f"[!] Unable to get weather forecast from API: {e}")
            try:
                with open(weather_file, "r") as f:
                    weather_long = json.load(f)
                    weather_long["time"] = [
                        datetime.fromtimestamp(x, tz=self.timezone)
                        for x in weather_long["time"]
                    ]
                if weather_long["time"][-1] >= datetime.fromtimestamp(
                    time.time(), tz=self.timezone
                ) + timedelta(hours=48):
                    self.log("A valid weather forecast is available locally.")
                    time_late = weather_long["time"][0] - datetime.now(self.timezone)
                    hours_late = int(time_late.total_seconds() / 3600)
                    wf = weather_long
                    for key in wf:
                        wf[key] = wf[key][hours_late : hours_late + 48]
                else:
                    self.log(
                        "No valid weather forecasts available locally. Using coldest of the current month."
                    )
                    current_month = datetime.now().month - 1
                    wf = {
                        "time": [
                            datetime.now(tz=self.timezone) + timedelta(hours=1 + x)
                            for x in range(48)
                        ],
                        "oat": [self.coldest_oat_by_month[current_month]] * 48,
                        "ws": [0] * 48,
                    }
            except Exception as e:
                self.log(
                    "No valid weather forecasts available locally. Using coldest of the current month."
                )
                current_month = datetime.now().month - 1
                wf = {
                    "time": [
                        datetime.now(tz=self.timezone) + timedelta(hours=1 + x)
                        for x in range(48)
                    ],
                    "oat": [self.coldest_oat_by_month[current_month]] * 48,
                    "ws": [0] * 48,
                }

        self.weather_forecast = {
            "oat": wf["oat"],
            "ws": wf["ws"],
        }

    async def get_real_time_price(self) -> float:
        '''Returns current 5min real-time price (LMP+Dist) in USD/MWh'''
        '''IMPORTANT: WE ARE NOT USING THE REAL-TIME PRICE YET, WE ARE USING PERFECT FORECASTED PRICE FOR NOW'''
        try:
            if datetime.now().minute < 55:
                price = await self.read_forecasted_price_for_now()
                return price
            else:
                top_of_hour_timestamp = int(time.time()//3600) * 3600 + 3600
                time_until_top_of_hour = int(top_of_hour_timestamp - time.time())
                await asyncio.sleep(min(time_until_top_of_hour, 5))
                price = await self.read_forecasted_price_for_now()
                return price
        except Exception as e:
            self.log(f"Error getting real-time price: {e}")
            return 0
        # try:
        #     url = "https://price-service.electricity.works/hw1-isone-me-versant-keene-ps/gw0-realtime-price"
        #     async with httpx.AsyncClient() as client:
        #         response = await client.get(url)
        #         if response.status_code == 200:
        #             self.log("Successfully received prices from API")
        #             data = response.json()
        #             price = float(data['Energy'])
        #             return price
        #         else:
        #             self.log(f"Failed to receive prices from API, status code: {response.status_code}")
        #             raise Exception("Failed to receive prices.")
        # except Exception as e:
        #     self.log(f"Error getting current price: {e}")
        #     try:
        #         self.log("Attempt to use the forecast price instead of current price")
        #         price = await self.read_forecasted_price_for_now()
        #         return price
        #     except Exception as e:
        #         self.log(f"Error getting forecast price: {e}")
        #         return 0

    async def get_price_forecast_48h(self) -> None:
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
                        reg_usd_per_mwh=[0] * len(data['LmpList']),
                    )
                    self.log(f"- LMP USD/MWh {self.price_forecast.lmp_usd_per_mwh}")
                    self.log(f"- Total energy USD/MWh {[round(x,2) for x in self.price_forecast.total_energy]}")
                    
                    # Save price forecast to a local CSV file
                    prices_file = Path(f"{self.settings.paths.data_dir}/price_forecast.csv")
                    # Check if current hour's data exists in the existing file
                    current_hour_row = None
                    if prices_file.exists():
                        current_hour_timestamp = data['HourStartS'][0] - 3600
                        with open(prices_file, 'r', newline='') as f:
                            reader = csv.reader(f)
                            header = next(reader)
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
                reg_usd_mwh = [0.0] * len(rows)

                # Crop the beginning of the CSV and extend the end to get a forecast for the next 48 hours
                time_now = time.time()
                timestamps_forecast = [t for t in timestamps if t > time_now]
                hours_available = len(timestamps_forecast)
                if not hours_available:
                    raise Exception("No forecasts available for the next hours!")
                dp_forecast_usd_per_mwh = [p for p,t in zip(dist_usd_mwh, timestamps) if t > time_now]
                lmp_forecast_usd_per_mwh = [p for p,t in zip(lmp_usd_mwh, timestamps) if t > time_now]
                reg_forecast_usd_per_mwh = [p for p,t in zip(reg_usd_mwh, timestamps) if t > time_now]
                if hours_available < 48:
                    dp_forecast_usd_per_mwh = dp_forecast_usd_per_mwh + [dp_forecast_usd_per_mwh[-1]] * (48-len(dp_forecast_usd_per_mwh))
                    lmp_forecast_usd_per_mwh = lmp_forecast_usd_per_mwh + [lmp_forecast_usd_per_mwh[-1]] * (48-len(lmp_forecast_usd_per_mwh))
                    reg_forecast_usd_per_mwh = reg_forecast_usd_per_mwh + [reg_forecast_usd_per_mwh[-1]] * (48-len(reg_forecast_usd_per_mwh))

                # Update the price forecast
                self.price_forecast = PriceForecast(
                    dp_usd_per_mwh=dp_forecast_usd_per_mwh,
                    lmp_usd_per_mwh=lmp_forecast_usd_per_mwh,
                    reg_usd_per_mwh=reg_forecast_usd_per_mwh,
                )
                self.log("Successfully read price forecast from local CSV.")
                self.log(f"- LMP USD/MWh {self.price_forecast.lmp_usd_per_mwh}")
                self.log(f"- Total energy USD/MWh {[round(x,2) for x in self.price_forecast.total_energy]}")

            except Exception as e:
                self.log(f"Could not get a price forecast from the local CSV file: {e}.")
                await self.send_glitch(f"Failed to read price forecast from local CSV file: {e}", log_level=LogLevel.Error)

    async def read_forecasted_price_for_now(self) -> float:
        """Returns the forecasted price for this hour (LMP + Dist) in USD/MWh"""
        try:
            prices_file = Path(f"{self.settings.paths.data_dir}/price_forecast.csv")
            if prices_file.exists():
                start_of_hour_timestamp = int(time.time()//3600) * 3600
                with open(prices_file, 'r', newline='') as f:
                    reader = csv.reader(f)
                    next(reader)
                    rows = list(reader)
                # Find the row with matching timestamp
                for row in rows:
                    if float(row[0]) == start_of_hour_timestamp:
                        self.log("A valid price forecast for this hour was available locally.")
                        price = float(row[1]) + float(row[2])  # dist + lmp
                        return price
                raise Exception(f"{prices_file} does not have a price forecast for this hour.")
            else:
                raise Exception(f"{prices_file} does not exist.")
        except Exception as e:
            self.log(f"Failed: {e}")
            await self.send_glitch(f"Error in read_forecasted_price_for_now: {e}", log_level=LogLevel.Error)
            return 0

    async def fake_market_maker(self):
        while True:
            # Calculate the time to the next top of the hour
            now = time.time()
            next_top_of_hour = (
                int(now // 3600) + 1
            ) * 3600  # next top of the hour in seconds
            sleep_time = next_top_of_hour - now

            # Sleep until the top of the hour
            await asyncio.sleep(sleep_time)
            await self.send_latest_price()

    async def send_latest_price(self) -> None:
        now = time.time()
        slot_start_s = int(now) - int(now) % 3600
        mtn = MarketTypeName.rt60gate5.value
        market_slot_name = f"e.{mtn}.{Atn.P_NODE}.{slot_start_s}"
        usd_per_mwh = await self.get_real_time_price()
        price = LatestPrice(
                FromGNodeAlias=Atn.P_NODE,
                PriceTimes1000=int(usd_per_mwh * 1000),
                PriceUnit=MarketPriceUnit.USDPerMWh,
                MarketSlotName=market_slot_name,
                MessageId=str(uuid.uuid4()),
            )
        self.log(f"Trying to Broadcasting price(x1000) {usd_per_mwh} at the top of the hour.")
        try:
            self.services.send_threadsafe(
                Message(Src=self.name, Dst=self.name, Payload=price)
            )
        except Exception as e:
            self.log(f"Problem generating or sending a LatestPrice: {e}")

    async def send_glitch(self, summary, details="", log_level=LogLevel.Info):
        glitch = Glitch(
            FromGNodeAlias=self.layout.atn_g_node_alias,
            Node=self.node.name,
            Type=log_level,
            Summary=summary,
            Details=details,
            CreatedMs=int(time.time() * 1000)
        )
        self.services.send_threadsafe(Message(Src=self.name, Dst=self.name, Payload=glitch))
        self.log("Sent glitch")

    def log(self, note: str) -> None:
        log_str = f"[atn] {note}"
        self.services.logger.error(log_str)

    def set_alpha(self, alpha: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "AlphaTimes10": int(alpha * 10)}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set alpha! {e}")

    def set_beta(self, beta: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "BetaTimes100": int(beta * 100)}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set beta! {e}")

    def set_gamma(self, gamma: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "GammaEx6": int(gamma * 1e6)}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set gamma! {e}")

    def set_intermediate_power(self, intermediate_power: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {
                        **self.ha1_params.model_dump(),
                        "IntermediatePowerKw": intermediate_power,
                    }
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set intermediate power! {e}")

    def set_intermediate_rswt(self, intermediate_rswt: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {
                        **self.ha1_params.model_dump(),
                        "IntermediateRswtF": int(intermediate_rswt),
                    }
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set intermediate rswt! {e}")

    def set_dd_power(self, dd_power: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "DdPowerKw": dd_power}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set DdPowerKw! {e}")

    def set_dd_rswt(self, dd_rswt: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "DdRswtF": dd_rswt}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set DdRswt! {e}")

    def set_dd_delta_t(self, dd_delta_t: float) -> None:
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "DdDeltaTF": dd_delta_t}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set DdDeltaTF! {e}")
    
    def set_load_overestimation_percent(self, load_overestimation_percent: float) -> None:
        if load_overestimation_percent < 0 or load_overestimation_percent > 100:
            self.log("Invalid entry, load_overestimation_percent should be a value between 0 and 100")
            return
        if self.ha1_params is None:
            self.send_layout()
        else:
            try:
                new = Ha1Params.model_validate(
                    {**self.ha1_params.model_dump(), "LoadOverestimationPercent": load_overestimation_percent}
                )
                self.send_new_params(new)
            except Exception as e:
                self.logger.error(f"Failed to set LoadOverestimationPercent! {e}")

    def set_keep_seconds(self, val: int = 0) -> None:
        self.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromHandle=f"{H0N.atn}",
                    ToHandle=f"{H0N.atn}.{H0N.atomic_ally}",
                    AboutName=H0N.sieg_loop,
                    Value=val,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
            )
        )

    def reset_keep_seconds(self, new_seconds: float) -> None:
        self.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=ResetHpKeepValue(
                    FromHandle=f"{H0N.atn}",
                    ToHandle=f"{H0N.atn}.{H0N.atomic_ally}",
                    HpKeepSecondsTimes10=round(new_seconds * 10),
                ),
            )
        )

    def send_harder(self, seconds: int) -> None:
        self.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SiegLoopEndpointValveAdjustment(
                    FromHandle=f"{H0N.atn}",
                    ToHandle=f"{H0N.atn}.{H0N.atomic_ally}",
                    HpKeepPercent=0,
                    Seconds=seconds,
                ),
            )
        )

    def set_lwt_control_params(self,
        proportional_gain: float = 5.0,
        integral_gain: float = 2,
        derivative_gain: float = 1,
        control_interval_seconds: int = 5,
        t1: int = 15,
        t2: int = 65
    ) -> None:
        self.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SetLwtControlParams(
                    FromHandle=H0N.atn,
                    ToHandle=f"{H0N.atn}.{H0N.atomic_ally}",
                    ProportionalGain=proportional_gain,
                    IntegralGain=integral_gain,
                    DerivativeGain=derivative_gain,
                    ControlIntervalSeconds=control_interval_seconds,
                    T1=t1,
                    T2=t2,
                ),
            )
        )

    def keep_harder(self, seconds: int) -> None:
        self.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=SiegLoopEndpointValveAdjustment(
                    FromHandle=f"{H0N.atn}",
                    ToHandle=f"{H0N.atn}.{H0N.atomic_ally}",
                    HpKeepPercent=100,
                    Seconds=seconds,
                ),
            )
        )

    def set_dist_010(self, val: int = 30) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromHandle="auto",
                    ToHandle="auto.dist-010v",
                    AboutName="dist-010v",
                    Value=val,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
            )
        )

    def set_primary_010(self, val: int = 50) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromHandle="auto",
                    ToHandle="auto.primary-010v",
                    AboutName="primary-010v",
                    Value=val,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
            )
        )

    def set_store_010(self, val: int = 30) -> None:
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self.scada.name,
                Payload=AnalogDispatch(
                    FromGNodeAlias=self.layout.atn_g_node_alias,
                    FromHandle="auto",
                    ToHandle="auto.store-010v",
                    AboutName="store-010v",
                    Value=val,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=int(time.time() * 1000),
                ),
            )
        )

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

"""Implements MultipurposeSensor via SyncThreadActor and MultipurposeSensorDriverThread.
A helper class, MultipurposeSensorSetupHelper,
isolates code used only in  MultipurposeSensorDriverThread constructor. """
import importlib
import importlib.util
import sys
import time
import typing
from typing import Dict, List, Optional

from drivers.multipurpose_sensor.multipurpose_sensor_driver import \
    MultipurposeSensorDriver
from gwproactor import SyncThreadActor
from gwproactor.sync_thread import SyncAsyncInteractionThread
from gwproto import Message
from gwproto.data_classes.components.ads111x_based_component import \
    Ads111xBasedComponent
from gwsproto.data_classes.house_0_names import H0N
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.hardware_layout import HardwareLayout
from gwproto.data_classes.sh_node import ShNode
from gwproto.enums import MakeModel
from gwproto.message import Header
from gwproto.named_types import AdsChannelConfig, SyncedReadings
from gwsproto.named_types import Glitch

from actors.config import ScadaSettings

from actors.scada_interface import ScadaInterface

UNKNOWNMAKE__UNKNOWNMODEL__MODULE_NAME = (
    "drivers.multipurpose_sensor.unknown_multipurpose_sensor_driver"
)
UNKNOWNMAKE__UNKNOWNMODEL__CLASS_NAME = "UnknownMultipurposeSensorDriver"


class MpDriverThreadSetupHelper:
    """A helper class to isolate code only used in construction of MultipurposeSensorDriverThread"""

    node: ShNode
    settings: ScadaSettings
    hardware_layout: HardwareLayout
    component: Ads111xBasedComponent

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
    ):
        if not isinstance(node.component, Ads111xBasedComponent):
            raise ValueError(
                "ERROR. MultipurposeSensorDriverThread requires node with  Ads111xBasedComponent. "
                f"Received node {node.Name} with componet type {type(node.component)}"
            )
        self.node = node
        self.settings = settings
        self.hardware_layout = hardware_layout
        self.component = typing.cast(Ads111xBasedComponent, node.component)

    def make_driver(self) -> MultipurposeSensorDriver:
        driver_module_name = ""
        driver_class_name = ""
        cac = self.component.cac
        if cac.MakeModel == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            driver_module_name = UNKNOWNMAKE__UNKNOWNMODEL__MODULE_NAME
            driver_class_name = UNKNOWNMAKE__UNKNOWNMODEL__CLASS_NAME
        elif cac.MakeModel == MakeModel.GRIDWORKS__TSNAP1:
            driver_module_name = "drivers.multipurpose_sensor.gridworks_tsnap1__multipurpose_sensor_driver"
            driver_class_name = "GridworksTsnap1_MultipurposeSensorDriver"
            for module_name in [
                "board",
                "busio",
                "adafruit_ads1x15",
                "adafruit_ads1x15.ads1115",
                "adafruit_ads1x15.analog_in",
            ]:
                found = importlib.util.find_spec(module_name)
                if found is None:
                    driver_module_name = UNKNOWNMAKE__UNKNOWNMODEL__MODULE_NAME
                    driver_class_name = UNKNOWNMAKE__UNKNOWNMODEL__CLASS_NAME
                    break
        if not driver_module_name or not driver_class_name:
            raise NotImplementedError(
                f"No MultipurposeSensor driver yet for {cac.MakeModel}"
            )
        if driver_module_name not in sys.modules:
            importlib.import_module(driver_module_name)
        driver_class = getattr(sys.modules[driver_module_name], driver_class_name)
        return driver_class(component=self.component, settings=self.settings)


class MultipurposeSensorDriverThread(SyncAsyncInteractionThread):

    FASTEST_POLL_PERIOD_MS = 40
    driver: MultipurposeSensorDriver
    cfg_by_ch: Dict[DataChannel, AdsChannelConfig]
    my_channels: List[DataChannel]
    last_reported_telemetry_value: Dict[str, Optional[int]]  # channel name to value
    latest_telemetry_value: Dict[str, Optional[int]]
    _last_sampled_s: Dict[str, Optional[int]]
    _telemetry_destination: str
    _hardware_layout: HardwareLayout

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
        telemetry_destination: str,
        responsive_sleep_step_seconds=0.01,
        daemon: bool = True,
    ):
        super().__init__(
            name=node.Name,
            responsive_sleep_step_seconds=responsive_sleep_step_seconds,
            daemon=daemon,
        )
        self._hardware_layout = hardware_layout
        self.component = typing.cast(Ads111xBasedComponent, node.component)
        self.poll_period_ms = max(
            self.FASTEST_POLL_PERIOD_MS,
            self.component.cac.MinPollPeriodMs,
        )
        self._telemetry_destination = telemetry_destination
        my_channel_names = {x.ChannelName for x in self.component.gt.ConfigList}
        self.my_channels = [
            ch
            for ch in self._hardware_layout.data_channels.values()
            if ch.AboutNodeName in my_channel_names
        ]
        setup_helper = MpDriverThreadSetupHelper(node, settings, hardware_layout)
        self.cfg_by_ch = {
            self._hardware_layout.data_channels[cfg.ChannelName]: cfg
            for cfg in self.component.gt.ConfigList
        }
        self.driver = setup_helper.make_driver()
        self.last_reported_telemetry_value = {ch.Name: None for ch in self.my_channels}
        self.latest_telemetry_value = {ch.Name: None for ch in self.my_channels}
        self._last_sampled_s = {ch.Name: None for ch in self.my_channels}

    def _preiterate(self) -> None:
        result = self.driver.start()
        if not result.is_ok():
            raise Exception(
                "Multipurpose sensor driver should not return error on init!"
            )
        outcome = result.value
        # There was a problem on initialization
        if len(outcome.comments) > 0:
            payload = Glitch(
                FromGNodeAlias=self._hardware_layout.scada_g_node_alias,
                Node=self.name,
                Type=outcome.get_highest_level(),
                Summary="TSnapStartupWarning",
                Details=outcome.comments_to_details(),
            )
            message = Message(
                header=Header(Src=self.name, Dst=H0N.atn,  MessageType=payload.TypeName),
                Payload=payload,
            )
            # TODO: add analog temp logging
            self._put_to_async_queue(message)

    def _iterate(self) -> None:
        start_s = time.time()
        self.poll_sensor()
        report_list = [
            ch for ch in self.my_channels if self.should_report_telemetry_reading(ch)
        ]
        if report_list:
            self.report_sampled_telemetry_values(report_list)
        sleep_time_ms = self.poll_period_ms
        delta_ms = 1000 * (time.time() - start_s)
        if delta_ms < self.poll_period_ms:
            sleep_time_ms -= delta_ms
        self._iterate_sleep_seconds = sleep_time_ms / 1000

    def poll_sensor(self):
        read = self.driver.read_telemetry_values(self.my_channels)
        if not read.is_ok():
            raise Exception(
                "read_telemetry_value is not supposed to return an exception!"
            )
        outcome = read.value
        read_by_ch_name = outcome.value
        for ch in self.my_channels:
            if ch.Name in read_by_ch_name:
                # Clears stale data when returns None
                self.latest_telemetry_value[ch.Name] = read_by_ch_name[ch.Name]

        if len(outcome.comments) > 0:
            self.outcome = outcome
            payload = Glitch(
                FromGNodeAlias=self._hardware_layout.scada_g_node_alias,
                Node=self.name,
                Type=outcome.get_highest_level(),
                Summary="TSnapReadIssue",
                Details=outcome.comments_to_details(),
            )
            message = Message(
                header=Header(Src=self.name, Dst=H0N.atn, MessageType=payload.TypeName),
                Payload=payload,
            )
            # TODO: add analog temp logging
            self._put_to_async_queue(message)

    def report_sampled_telemetry_values(self, channel_list: List[DataChannel]):

        self._put_to_async_queue(
            Message(
                Src=self.name,
                Dst=self._telemetry_destination,
                Payload=SyncedReadings(
                    ChannelNameList=[ch.Name for ch in channel_list],
                    ValueList=list(map(
                        lambda x: self.latest_telemetry_value[x.Name],
                        channel_list,
                    )),
                    ScadaReadTimeUnixMs=int(1000 * time.time())
                )
            )
        )
        for ch in channel_list:
            self._last_sampled_s[ch.Name] = int(time.time())
            self.last_reported_telemetry_value[ch.Name] = self.latest_telemetry_value[
                ch.Name
            ]

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def value_exceeds_async_threshold(self, ch: DataChannel) -> bool:
        """This telemetry tuple is supposed to report asynchronously on change, with
        the amount of change required (as a function of the absolute max value) determined
        in the Config.
        """
        telemetry_config = self.cfg_by_ch[ch]
        if (
            telemetry_config.AsyncCapture
            and telemetry_config.AsyncCaptureDelta is not None
        ):
            abs_telemetry_delta = abs(
                self.latest_telemetry_value[ch.Name]
                - self.last_reported_telemetry_value[ch.Name]
            )
            #new = self.latest_telemetry_value[ch.Name]
            # if ch.Name == 'dist-swt':   
            #     print(f"dist-swt {round(new / 1000, 3)} C" )
            if abs_telemetry_delta > telemetry_config.AsyncCaptureDelta:
                # if ch.Name == 'dist-swt':
                #     print("#####################")
                #     print("SENDING!")
                #     print("#####################")
                return True
        return False

    def should_report_telemetry_reading(self, ch: DataChannel) -> bool:
        if self.latest_telemetry_value[ch.Name] is None:
            self.last_reported_telemetry_value[ch.Name] = None # so that when the driver reads again it reports
            return False
        if (
            self._last_sampled_s[ch.Name] is None
            or self.last_reported_telemetry_value[ch.Name] is None
        ):
            return True
        if (
            time.time() - self._last_sampled_s[ch.Name]
            > self.cfg_by_ch[ch].CapturePeriodS
        ):
            return True
        if self.value_exceeds_async_threshold(ch):
            return True
        return False


class MultipurposeSensor(SyncThreadActor):
    def __init__(
        self,
        name: str,
        services: ScadaInterface,
        settings: Optional[ScadaSettings] = None,
    ):

        super().__init__(
            name=name,
            services=services,
            sync_thread=MultipurposeSensorDriverThread(
                node=services.hardware_layout.node(name),
                settings=services.settings if settings is None else settings,
                hardware_layout=services.hardware_layout,
                telemetry_destination=services.name,
            ),
        )

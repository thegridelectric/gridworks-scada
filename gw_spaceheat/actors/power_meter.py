"""Implements PowerMeter via SyncThreadActor and PowerMeterDriverThread. A helper class, DriverThreadSetupHelper,
isolates code used only in PowerMeterDriverThread constructor. """
import logging
import time
import typing
from typing import Dict
from typing import List
from typing import Optional

from gwproactor.logger import LoggerOrAdapter
from gwproto import Message
from gwproto.enums import TelemetryName

from actors.config import ScadaSettings
from gwsproto.data_classes.house_0_names import H0N
from gwproactor import SyncThreadActor
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from gwproto.data_classes.hardware_layout import HardwareLayout
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.sh_node import ShNode
from drivers.exceptions import DriverWarning
from drivers.power_meter.egauge_4030__power_meter_driver import EGuage4030_PowerMeterDriver
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import (
    GridworksSimPm1_PowerMeterDriver,
)
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from drivers.power_meter.unknown_power_meter_driver import UnknownPowerMeterDriver
from gwproactor.message import InternalShutdownMessage
from gwproactor.sync_thread import SyncAsyncInteractionThread
from gwproactor import Problems
from gwproto.enums import MakeModel
from gwproto.named_types import ElectricMeterChannelConfig, PowerWatts, SyncedReadings

from scada_app_interface import ScadaAppInterface


class HWUidMismatch(DriverWarning):
    expected: str
    got: str

    def __init__(
            self,
            expected: str,
            got: str,
            msg: str = "",
    ):
        super().__init__(msg)
        self.expected = expected
        self.got = got

    def __str__(self):
        s = self.__class__.__name__
        super_str = super().__str__()
        if super_str:
            s += f" <{super_str}>"
        s += (
            f"  exp: {self.expected}\n"
            f"  got: {self.got}"
        )
        return s


class DriverThreadSetupHelper:
    """A helper class to isolate code only used in construction of PowerMeterDriverThread"""

    FASTEST_POWER_METER_POLL_PERIOD_MS = 40
    DEFAULT_ASYNC_REPORTING_THRESHOLD = 0.05

    node: ShNode
    settings: ScadaSettings
    hardware_layout: HardwareLayout
    component: ElectricMeterComponent
    logger: LoggerOrAdapter

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
        logger: LoggerOrAdapter,
    ):
        if not isinstance(node.component, ElectricMeterComponent):
            raise ValueError(
                "ERROR. PowerMeterDriverThread requires node with ElectricMeterComponent. "
                f"Received node {node.Name} with componet type {type(node.component)}"
            )
        self.node = node
        self.settings = settings
        self.hardware_layout = hardware_layout
        self.component = typing.cast(ElectricMeterComponent, node.component)
        self.logger = logger

    def make_power_meter_driver(self) -> PowerMeterDriver:
        cac = self.component.cac
        if cac.MakeModel == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            driver = UnknownPowerMeterDriver(component=self.component, settings=self.settings)
        elif cac.MakeModel == MakeModel.GRIDWORKS__SIMPM1:
            driver = GridworksSimPm1_PowerMeterDriver(component=self.component, settings=self.settings)
        elif cac.MakeModel == MakeModel.EGAUGE__4030:
            driver = EGuage4030_PowerMeterDriver(
                component=self.component,
                settings=self.settings,
                logger=self.logger,
            )
        else:
            raise NotImplementedError(
                f"No ElectricMeter driver yet for {cac.MakeModel}"
            )
        return driver

    def make_eq_reporting_config(self) -> Dict[DataChannel, ElectricMeterChannelConfig]:
        response_dict: Dict[DataChannel, ElectricMeterChannelConfig] = {}
        for config in self.component.gt.ConfigList:
            ch = self.hardware_layout.data_channels[config.ChannelName]
            response_dict[ch] = config
        return response_dict

    def get_transactive_nameplate_watts(self) -> Dict[DataChannel, int]:
        response_dict: Dict[DataChannel, int] = {}
        for config in self.component.gt.ConfigList:
            ch = self.hardware_layout.data_channels[config.ChannelName]
            if ch.InPowerMetering:
                response_dict[ch] = ch.about_node.NameplatePowerW
        return response_dict


class PowerMeterDriverThread(SyncAsyncInteractionThread):
    eq_reporting_config: Dict[DataChannel, ElectricMeterChannelConfig]
    driver: PowerMeterDriver
    transactive_nameplate_watts: Dict[DataChannel, int]
    last_reported_agg_power_w: Optional[int] = None
    last_reported_telemetry_value: Dict[DataChannel, Optional[int]]
    latest_telemetry_value: Dict[DataChannel, Optional[int]]
    _last_sampled_s: Dict[DataChannel, Optional[int]]
    async_power_reporting_threshold: float
    _telemetry_destination: str
    _hardware_layout: HardwareLayout
    _hw_uid: str = ""

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
        telemetry_destination: str,
        responsive_sleep_step_seconds=0.01,
        daemon: bool = True,
        logger: Optional[LoggerOrAdapter] = None,
    ):
        super().__init__(
            name=node.Name,
            responsive_sleep_step_seconds=responsive_sleep_step_seconds,
            daemon=daemon,
            logger=logger,
        )
        self._hardware_layout = hardware_layout
        self._telemetry_destination = telemetry_destination
        setup_helper = DriverThreadSetupHelper(
            node,
            settings,
            hardware_layout,
            logger=logger
        )
        self.eq_reporting_config = setup_helper.make_eq_reporting_config()
        self.driver = setup_helper.make_power_meter_driver()
        self.transactive_nameplate_watts = setup_helper.get_transactive_nameplate_watts()
        self.last_reported_agg_power_w: Optional[int] = None
        component: ElectricMeterComponent = typing.cast(ElectricMeterComponent, node.component)
        my_channel_names = [cfg.ChannelName for cfg in component.gt.ConfigList]
        self.my_channels = [hardware_layout.data_channels[name] for name in my_channel_names]
        self._validate_channels_with_component(component)
        self.last_reported_telemetry_value = {
            ch: None for ch in self.my_channels
        }
        self.latest_telemetry_value = {
            ch: None for ch in self.my_channels
        }
        self._last_sampled_s = {
            ch: None for ch in self.my_channels
        }
        self.async_power_reporting_threshold = settings.async_power_reporting_threshold

    def _validate_channels_with_component(self, component: ElectricMeterComponent) -> None:
        for channel in self.my_channels:
            if channel.TelemetryName != TelemetryName.PowerW:
                raise ValueError(f"read_power_w got a channel with {channel.TelemetryName}")
            channel_config = next((cfg for cfg in component.gt.ConfigList if cfg.ChannelName == channel.Name), None)
            if channel_config is None:
                raise Exception(f"Reading power for channel {channel.Name} but this is not in the ConfigList!")
            self.driver.validate_config(channel_config)

    def _report_problems(self, problems: Problems, tag: str, log_event: bool = False):
        event = problems.problem_event(
            summary=f"Driver problems: {tag} for {self.driver.component}",
        )
        message = Message(Payload=event)
        if log_event and self._logger.isEnabledFor(logging.DEBUG):
            self._logger.info(
                "PowerMeter event:\n"
                f"{event}"
            )
            self._logger.info(
                "PowerMeter message\n"
                f"{message.model_dump_json(indent=2)}"
            )
        self._put_to_async_queue(message)

    def _preiterate(self) -> None:
        result = self.driver.start()
        if result.is_ok():
            if result.value.warnings:
                self._report_problems(Problems(warnings=result.value.warnings), "startup warning")
        else:
            self._report_problems(Problems(errors=[result.err()]), "startup error")
            self._put_to_async_queue(
                InternalShutdownMessage(Src=self.name, Reason=f"Driver start error for {self.name}")
            )

    def _ensure_hardware_uid(self):
        if not self._hw_uid:
            hw_uid_read_result = self.driver.read_hw_uid()
            if hw_uid_read_result.is_ok():
                if hw_uid_read_result.value.value:
                    self._hw_uid = hw_uid_read_result.value.value.strip("\u0000")
                    if (
                        self.driver.component.gt.HwUid
                        and self._hw_uid != self.driver.component.gt.HwUid
                    ):
                        self._report_problems(
                            Problems(
                                warnings=[
                                    HWUidMismatch(
                                        expected=self.driver.component.gt.HwUid,
                                        got=self._hw_uid,
                                    )
                                ]
                            ),
                            "Hardware UID read"
                        )
            else:
                raise hw_uid_read_result.value

    def _iterate(self) -> None:
        start_s = time.time()
        self._ensure_hardware_uid()
        self.update_latest_value_dicts()
        if self.should_report_aggregated_power():
            self.report_aggregated_power_w()
        channel_report_list = [
            ch
            for ch in self.my_channels
            if self.should_report_telemetry_reading(ch)
        ]
        if channel_report_list:
            self.report_sampled_telemetry_values(channel_report_list)
        sleep_time_ms = self.driver.component.cac.MinPollPeriodMs
        delta_ms = 1000 * (time.time() - start_s)
        if delta_ms < sleep_time_ms:
            sleep_time_ms -= delta_ms
        self._iterate_sleep_seconds = sleep_time_ms / 1000

    def update_latest_value_dicts(self):
        logged_one = False
        for ch in self.my_channels:
            read = self.driver.read_telemetry_value(ch)
            if read.is_ok():
                if read.value.value is not None:
                    self.latest_telemetry_value[ch] = read.value.value
                if read.value.warnings:
                    log_event = False
                    if not logged_one and self._logger.isEnabledFor(logging.DEBUG):
                        logged_one = True
                        log_event = True
                        self._logger.info(f"PowerMeter: TryConnectResult:\n{read.value}")
                        problems = Problems(warnings=read.value.warnings)
                        self._logger.info(f"PowerMeter: Problems:\n{problems}")
                    self._report_problems(
                        problems=Problems(warnings=read.value.warnings),
                        tag="read warnings",
                        log_event=log_event
                    )
            else:
                raise read.value

    def report_sampled_telemetry_values(
        self, channel_report_list: List[DataChannel]
    ):
        try:
            msg = Message(
                    Src=self.name,
                    Dst= H0N.primary_scada,
                    Payload=SyncedReadings(
                        ChannelNameList=[ch.Name for ch in channel_report_list],
                        ValueList=[self.latest_telemetry_value[ch] for ch in channel_report_list],
                        ScadaReadTimeUnixMs=int(1000 * time.time())
                    )
                )
            self._put_to_async_queue(msg)
            for ch in channel_report_list:
                self._last_sampled_s[ch] = int(time.time())
                self.last_reported_telemetry_value[ch] = self.latest_telemetry_value[ch]
        except Exception as e:
            self._report_problems(Problems(warnings=[e, [self.latest_telemetry_value[ch] for ch in channel_report_list]]), "synced reading generation failure")

    def value_exceeds_async_threshold(self, ch: DataChannel) -> bool:
        """This telemetry tuple is supposed to report asynchronously on change, with
        the amount of change required (as a function of the absolute max value) determined
        in the EqConfig.
        """
        config = self.eq_reporting_config[ch]
        if config.AsyncCaptureDelta is None:
            return False
        last_reported_value = self.last_reported_telemetry_value[ch]
        latest_telemetry_value = self.latest_telemetry_value[ch]
        telemetry_delta = abs(latest_telemetry_value - last_reported_value)
        if telemetry_delta > config.AsyncCaptureDelta:
            return True
        return False

    def should_report_telemetry_reading(self, ch: DataChannel) -> bool:
        """The telemetry data should get reported synchronously once every SamplePeriodS, and also asynchronously
        on a big enough change - both configured in the eq_config (eq for electrical quantity) config for this
        telemetry tuple.

        Note that SamplePeriodS will often be 300 seconds, which will also match the duration of each status message
        the Scada sends up to the cloud (GtShSimpleStatus.ReportingPeriodS).  The Scada will likely do this at the
        top of every 5 minutes - but not the power meter.. The point of the synchronous reporting is to
        get at least one reading for this telemetry tuple in the Scada's status report; it does not need to be
        at the beginning or end of the status report time period.
        """
        if self.latest_telemetry_value[ch] is None:
            return False
        if (
            self._last_sampled_s[ch] is None
            or self.last_reported_telemetry_value[ch] is None
        ):
            return True
        if (
            time.time() - self._last_sampled_s[ch]
            > self.eq_reporting_config[ch].CapturePeriodS
        ):
            return True
        if self.value_exceeds_async_threshold(ch):
            return True
        return False

    @property
    def latest_agg_power_w(self) -> Optional[int]:
        """Tracks the sum of the power of the all the nodes whose power is getting measured by the power meter"""
        latest_power_list = [
            v
            for k, v in self.latest_telemetry_value.items()
            if k in self.my_channels and k.InPowerMetering
        ]
        if None in latest_power_list:
            return None
        return int(sum(latest_power_list))

    @property
    def nameplate_agg_power_w(self) -> int:
        return int(sum(self.transactive_nameplate_watts.values()))

    def report_aggregated_power_w(self):
        message = Message(
            Src=self.name,
            Dst=H0N.primary_scada,
            Payload=PowerWatts(Watts=self.latest_agg_power_w)
        )
        self._put_to_async_queue(message)
        self.last_reported_agg_power_w = self.latest_agg_power_w


    def should_report_aggregated_power(self) -> bool:
        """Aggregated power is sent up asynchronously on change via a PowerWatts message, and the last aggregated
        power sent up is recorded in self.last_reported_agg_power_w."""
        if self.latest_agg_power_w is None:
            return False
        if self.nameplate_agg_power_w == 0:
            return False
        if self.last_reported_agg_power_w is None:
            return True
        abs_power_delta = abs(self.latest_agg_power_w - self.last_reported_agg_power_w)
        change_ratio = abs_power_delta / self.nameplate_agg_power_w
        if change_ratio > self.async_power_reporting_threshold:
            return True
        return False


class PowerMeter(SyncThreadActor):
    POWER_METER_LOGGER_NAME: str = "PowerMeter"

    def __init__(
        self,
        name: str,
        services: ScadaAppInterface,
        settings: Optional[ScadaSettings] = None,
    ):
        settings = settings or services.settings
        super().__init__(
            name=name,
            services=services,
            sync_thread=PowerMeterDriverThread(
                node=services.hardware_layout.node(name),
                settings=settings,
                hardware_layout=services.hardware_layout,
                telemetry_destination=services.name,
                logger=services.logger.add_category_logger(
                    self.POWER_METER_LOGGER_NAME,
                    level=settings.power_meter_logging_level,
                )
            ),
        )

    @property
    def sync_thread(self) -> PowerMeterDriverThread:
        if not isinstance(self._sync_thread, PowerMeterDriverThread):
            raise RuntimeError(
                f"ERROR. Unexpected type for sync_thread: {type(self._sync_thread)}"
            )
        return self._sync_thread

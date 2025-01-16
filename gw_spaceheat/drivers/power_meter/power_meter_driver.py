import logging
import time
from typing import Dict
from typing import List
from typing import Optional

from gwproto import Message
from gwproto.enums import TelemetryName
from result import Err
from result import Ok
from result import Result

from actors.message import PowerWattsMessage
from actors.message import SyncedReadingsMessage
from actors.scada_interface import ScadaInterface
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.sh_node import ShNode

from drivers.driver_result import DriverResult
from drivers.exceptions import DriverWarning
from gwproactor.message import InternalShutdownMessage
from gwproactor.sync_thread import SyncAsyncInteractionThread
from gwproactor import Problems
from gwproto.named_types import ElectricMeterChannelConfig

POWER_METER_LOGGER_NAME: str = "PowerMeter"

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


class PowerMeterDriver(SyncAsyncInteractionThread):
    eq_reporting_config: Dict[DataChannel, ElectricMeterChannelConfig]
    transactive_nameplate_watts: Dict[DataChannel, int]
    last_reported_agg_power_w: Optional[int] = None
    last_reported_telemetry_value: Dict[DataChannel, Optional[int]]
    latest_telemetry_value: Dict[DataChannel, Optional[int]]
    async_power_reporting_threshold: float
    my_channels: list[DataChannel]
    _last_sampled_s: Dict[DataChannel, Optional[int]]
    _telemetry_destination: str
    _hw_uid: str = ""
    _component: ElectricMeterComponent

    def __init__(self, node: ShNode, services: ScadaInterface) -> None:
        # def __init__(
        #     self,
        #     node: ShNode,
        #     settings: ScadaSettings,
        #     hardware_layout: HardwareLayout,
        #     telemetry_destination: str,
        #     responsive_sleep_step_seconds=0.01,
        #     daemon: bool = True,
        #     logger: Optional[LoggerOrAdapter] = None,
        # ):
            #     component=node.component,
            #     settings=services.settings,
            #     logger=services.logger.add_category_logger(
            #         POWER_METER_LOGGER_NAME,
            #         level=services.settings.power_meter_logging_level,
            #     ),
            # )
        if not isinstance(node.component, ElectricMeterComponent):
            raise ValueError(
                "ERROR. PowerMeterDriverThread requires node with ElectricMeterComponent. "
                f"Received node {node.Name} with component type {type(node.component)}"
            )
        self._component = node.component
        super().__init__(
            name=node.Name,
            responsive_sleep_step_seconds=0.05,
            daemon=True,
            logger=services.logger.add_category_logger(
                POWER_METER_LOGGER_NAME,
                level=services.settings.power_meter_logging_level,
            ),
        )
        self._telemetry_destination = services.name
        layout = services.hardware_layout

        self.eq_reporting_config = {
            layout.data_channels[config.ChannelName]: config
            for config in self._component.gt.ConfigList
        }
        self.my_channels = [
            layout.data_channels[config.ChannelName]
            for config in self._component.gt.ConfigList
        ]
        for channel in self.my_channels:
            if channel.TelemetryName != TelemetryName.PowerW:
                raise ValueError(f"read_power_w got a channel with {channel.TelemetryName}")
            self._validate_config(self.eq_reporting_config[channel])
        self.transactive_nameplate_watts = {
            ch: ch.about_node.NameplatePowerW for ch in self.my_channels if ch.InPowerMetering
        }
        self.last_reported_agg_power_w: Optional[int] = None
        self.last_reported_telemetry_value = {
            ch: None for ch in self.my_channels
        }
        self.latest_telemetry_value = {
            ch: None for ch in self.my_channels
        }
        self._last_sampled_s = {
            ch: None for ch in self.my_channels
        }
        self.async_power_reporting_threshold = services.settings.async_power_reporting_threshold

    def _validate_config(self, config: ElectricMeterChannelConfig) -> None:
        ...

    def _report_problems(self, problems: Problems, tag: str, log_event: bool = False):
        event = problems.problem_event(
            summary=f"Driver problems: {tag} for {self._component}",
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

    def start(self) -> Result[DriverResult, Exception]:
        return Ok(DriverResult(True))

    def _preiterate(self) -> None:
        result = self.start()
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
            hw_uid_read_result = self.read_hw_uid()
            if hw_uid_read_result.is_ok():
                if hw_uid_read_result.value.value:
                    self._hw_uid = hw_uid_read_result.value.value.strip("\u0000")
                    if (
                        self._component.gt.HwUid
                        and self._hw_uid != self._component.gt.HwUid
                    ):
                        self._report_problems(
                            Problems(
                                warnings=[
                                    HWUidMismatch(
                                        expected=self._component.gt.HwUid,
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
        sleep_time_ms = self._component.cac.MinPollPeriodMs
        delta_ms = 1000 * (time.time() - start_s)
        if delta_ms < sleep_time_ms:
            sleep_time_ms -= delta_ms
        self._iterate_sleep_seconds = sleep_time_ms / 1000

    def update_latest_value_dicts(self):
        logged_one = False
        for ch in self.my_channels:
            read = self.read_telemetry_value(ch)
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
            msg = SyncedReadingsMessage(
                    src=self.name,
                    dst=self._telemetry_destination,
                    channel_name_list= [ch.Name for ch in channel_report_list],
                    value_list=[self.latest_telemetry_value[ch] for ch in channel_report_list],
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
        self._put_to_async_queue(
            PowerWattsMessage(
                src=self.name,
                dst=self._telemetry_destination,
                power=self.latest_agg_power_w,
            )
        )
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

    def read_hw_uid(self) -> Result[DriverResult[str | None], Exception]:
        raise NotImplementedError()

    def read_power_w(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError()

    def read_current_rms_micro_amps(self, channel: DataChannel) -> Result[DriverResult[int | None], Exception]:
        raise NotImplementedError()

    def read_telemetry_value(
        self,
        channel: DataChannel
    ) -> Result[DriverResult[int | None], Exception]:
        if channel.TelemetryName == TelemetryName.PowerW:
            return self.read_power_w(channel)
        elif channel.TelemetryName == TelemetryName.CurrentRmsMicroAmps:
            return self.read_current_rms_micro_amps(channel)
        else:
            return Err(ValueError(f"Driver {self} not set up to read {channel.TelemetryName}"))


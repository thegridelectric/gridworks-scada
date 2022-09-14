"""Implements PowerMeter via SyncThreadActor and PowerMeterDriverThread. A helper class, DriverThreadSetupHelper,
isolates code used only in PowerMeterDriverThread constructor. """

import asyncio
import time
import typing
from collections import OrderedDict
from typing import Optional, Dict, List

from actors2.actor import SyncThreadActor
from actors2.message import GsPwrMessage, MultipurposeSensorTelemetryMessage
from actors2.scada_interface import ScadaInterface
from config import ScadaSettings
from data_classes.components.electric_meter_component import ElectricMeterComponent
from data_classes.components.resistive_heater_component import ResistiveHeaterComponent
from data_classes.hardware_layout import HardwareLayout
from data_classes.sh_node import ShNode
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import (
    GridworksSimPm1_PowerMeterDriver,
)
from drivers.power_meter.openenergy_emonpi__power_meter_driver import (
    OpenenergyEmonpi_PowerMeterDriver,
)
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from drivers.power_meter.schneiderelectric_iem3455__power_meter_driver import (
    SchneiderElectricIem3455_PowerMeterDriver,
)
from drivers.power_meter.unknown_power_meter_driver import UnknownPowerMeterDriver
from named_tuples.telemetry_tuple import TelemetryTuple
from proactor.sync_thread import SyncAsyncInteractionThread, SyncAsyncQueueWriter
from schema.enums.make_model.spaceheat_make_model_100 import MakeModel
from schema.enums.role.sh_node_role_110 import Role
from schema.enums.telemetry_name.spaceheat_telemetry_name_100 import TelemetryName
from schema.enums.unit.spaceheat_unit_100 import Unit
from schema.gt.gt_eq_reporting_config.gt_eq_reporting_config import GtEqReportingConfig
from schema.gt.gt_eq_reporting_config.gt_eq_reporting_config_maker import (
    GtEqReportingConfig_Maker,
)
from schema.gt.gt_powermeter_reporting_config.gt_powermeter_reporting_config_maker import (
    GtPowermeterReportingConfig as ReportingConfig,
    GtPowermeterReportingConfig_Maker,
)


class DriverThreadSetupHelper:
    """A helper class to isolate code only used in construction of PowerMeterDriverThread"""

    FASTEST_POWER_METER_POLL_PERIOD_MS = 40
    DEFAULT_ASYNC_REPORTING_THRESHOLD = 0.05

    node: ShNode
    settings: ScadaSettings
    hardware_layout: HardwareLayout
    component: ElectricMeterComponent

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
    ):
        if not isinstance(node.component, ElectricMeterComponent):
            raise ValueError(
                "ERROR. PowerMeterDriverThread requires node with ElectricMeterComponent. "
                f"Received node {node.alias} with componet type {type(node.component)}"
            )
        self.node = node
        self.settings = settings
        self.hardware_layout = hardware_layout
        self.component = typing.cast(ElectricMeterComponent, node.component)

    def make_eq_reporting_config(self) -> Dict[TelemetryTuple, GtEqReportingConfig]:
        eq_reporting_config: Dict[TelemetryTuple, GtEqReportingConfig] = OrderedDict()
        for about_node in self.hardware_layout.all_metered_nodes:
            eq_reporting_config[
                TelemetryTuple(
                    AboutNode=about_node,
                    SensorNode=self.node,
                    TelemetryName=TelemetryName.CURRENT_RMS_MICRO_AMPS,
                )
            ] = GtEqReportingConfig_Maker(
                sh_node_alias=about_node.alias,
                report_on_change=True,
                telemetry_name=TelemetryName.CURRENT_RMS_MICRO_AMPS,
                unit=Unit.AMPS_RMS,
                exponent=6,
                sample_period_s=self.settings.seconds_per_report,
                async_report_threshold=self.settings.async_power_reporting_threshold,
            ).tuple
            eq_reporting_config[
                TelemetryTuple(
                    AboutNode=about_node,
                    SensorNode=self.node,
                    TelemetryName=TelemetryName.POWER_W,
                )
            ] = GtEqReportingConfig_Maker(
                sh_node_alias=about_node.alias,
                report_on_change=True,
                telemetry_name=TelemetryName.POWER_W,
                unit=Unit.W,
                exponent=0,
                sample_period_s=self.settings.seconds_per_report,
                async_report_threshold=self.settings.async_power_reporting_threshold,
            ).tuple
        return eq_reporting_config

    def make_reporting_config(
        self, eq_reporting_config_list: List[GtEqReportingConfig]
    ) -> ReportingConfig:
        if self.component.cac.update_period_ms is None:
            poll_period_ms = self.FASTEST_POWER_METER_POLL_PERIOD_MS
        else:
            poll_period_ms = max(
                self.FASTEST_POWER_METER_POLL_PERIOD_MS,
                self.component.cac.update_period_ms,
            )
        return GtPowermeterReportingConfig_Maker(
            reporting_period_s=self.settings.seconds_per_report,
            poll_period_ms=poll_period_ms,
            hw_uid=self.component.hw_uid,
            electrical_quantity_reporting_config_list=eq_reporting_config_list,
        ).tuple

    def make_power_meter_driver(self) -> PowerMeterDriver:
        cac = self.component.cac
        if cac.make_model == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            driver = UnknownPowerMeterDriver(component=self.component)
        elif cac.make_model == MakeModel.SCHNEIDERELECTRIC__IEM3455:
            driver = SchneiderElectricIem3455_PowerMeterDriver(component=self.component)
        elif cac.make_model == MakeModel.GRIDWORKS__SIMPM1:
            driver = GridworksSimPm1_PowerMeterDriver(component=self.component)
        elif cac.make_model == MakeModel.OPENENERGY__EMONPI:
            driver = OpenenergyEmonpi_PowerMeterDriver(
                component=self.component, settings=self.settings
            )
        else:
            raise NotImplementedError(
                f"No ElectricMeter driver yet for {cac.make_model}"
            )
        return driver

    @classmethod
    def get_resistive_heater_component(cls, node: ShNode) -> ResistiveHeaterComponent:
        if node.role != Role.BOOST_ELEMENT:
            raise ValueError(
                "This function should only be called for nodes that are boost elements"
            )
        if not isinstance(node.component, ResistiveHeaterComponent):
            raise ValueError(
                f"Node component has type {type(node.component)}. Requires type ResistiveHeaterComponent"
            )
        return typing.cast(ResistiveHeaterComponent, node.component)

    @classmethod
    def get_resistive_heater_nameplate_power_w(cls, node: ShNode) -> int:
        return cls.get_resistive_heater_component(node).cac.nameplate_max_power_w

    @classmethod
    def get_resistive_heater_nameplate_current_amps(cls, node: ShNode) -> float:
        """Note that all ShNodes of role BOOST_ELEMENT must have a non-zero RatedVoltageV and have a component
        of type ResistiveHeaterComponent.  Likewise, all ResistiveHeaterCacs have a positive NamePlateMaxPower.
        This is enforced by schema and not checked here."""
        return cls.get_resistive_heater_nameplate_power_w(node) / node.rated_voltage_v

    def get_nameplate_telemetry_value(self) -> Dict[TelemetryTuple, int]:
        response_dict: Dict[TelemetryTuple, int] = {}
        for about_node in self.hardware_layout.all_resistive_heaters:
            current_tt = TelemetryTuple(
                AboutNode=about_node,
                SensorNode=self.node,
                TelemetryName=TelemetryName.CURRENT_RMS_MICRO_AMPS,
            )
            nameplate_current_amps = self.get_resistive_heater_nameplate_current_amps(
                node=about_node
            )
            response_dict[current_tt] = int(10**6 * nameplate_current_amps)

            power_tt = TelemetryTuple(
                AboutNode=about_node,
                SensorNode=self.node,
                TelemetryName=TelemetryName.POWER_W,
            )
            nameplate_power_w = self.get_resistive_heater_nameplate_power_w(
                node=about_node
            )
            response_dict[power_tt] = int(nameplate_power_w)
        return response_dict


class PowerMeterDriverThread(SyncAsyncInteractionThread):

    eq_reporting_config: Dict[TelemetryTuple, GtEqReportingConfig]
    reporting_config: ReportingConfig
    driver: PowerMeterDriver
    nameplate_telemetry_value: Dict[TelemetryTuple, int]
    last_reported_agg_power_w: Optional[int] = None
    last_reported_telemetry_value: Dict[TelemetryTuple, Optional[int]]
    latest_telemetry_value: Dict[TelemetryTuple, Optional[int]]
    _last_sampled_s: Dict[TelemetryTuple, Optional[int]]
    async_power_reporting_threshold: float
    _telemetry_destination: str
    _hardware_layout: HardwareLayout

    def __init__(
        self,
        node: ShNode,
        settings: ScadaSettings,
        hardware_layout: HardwareLayout,
        telemetry_destination: str,
        channel: SyncAsyncQueueWriter,
        responsive_sleep_step_seconds=0.01,
        daemon: bool = True,
    ):
        super().__init__(
            channel=channel,
            name=node.alias,
            responsive_sleep_step_seconds=responsive_sleep_step_seconds,
            daemon=daemon,
        )
        self._hardware_layout = hardware_layout
        self._telemetry_destination = telemetry_destination
        setup_helper = DriverThreadSetupHelper(node, settings, hardware_layout)
        self.eq_reporting_config = setup_helper.make_eq_reporting_config()
        self.reporting_config = setup_helper.make_reporting_config(
            list(self.eq_reporting_config.values())
        )
        self.driver = setup_helper.make_power_meter_driver()
        self.nameplate_telemetry_value = setup_helper.get_nameplate_telemetry_value()
        self.last_reported_agg_power_w: Optional[int] = None
        self.last_reported_telemetry_value = {
            tt: None for tt in self._hardware_layout.all_power_meter_telemetry_tuples
        }
        self.latest_telemetry_value = {
            tt: None for tt in self._hardware_layout.all_power_meter_telemetry_tuples
        }
        self._last_sampled_s = {
            tt: None for tt in self._hardware_layout.all_power_meter_telemetry_tuples
        }
        self.async_power_reporting_threshold = settings.async_power_reporting_threshold

    def _preiterate(self) -> None:
        self.driver.start()

    def _iterate(self) -> None:
        start_s = time.time()
        self.update_latest_value_dicts()
        if self.should_report_aggregated_power():
            self.report_aggregated_power_w()
        telemetry_tuple_report_list = [
            tpl
            for tpl in self._hardware_layout.all_power_meter_telemetry_tuples
            if self.should_report_telemetry_reading(tpl)
        ]
        if telemetry_tuple_report_list:
            self.report_sampled_telemetry_values(telemetry_tuple_report_list)
        sleep_time_ms = self.reporting_config.PollPeriodMs
        delta_ms = 1000 * (time.time() - start_s)
        if delta_ms < self.reporting_config.PollPeriodMs:
            sleep_time_ms -= delta_ms
        self._iterate_sleep_seconds = sleep_time_ms / 1000

    def update_latest_value_dicts(self):
        for tt in self._hardware_layout.all_power_meter_telemetry_tuples:
            self.latest_telemetry_value[tt] = self.driver.read_telemetry_value(
                tt.TelemetryName
            )

    def report_sampled_telemetry_values(
        self, telemetry_sample_report_list: List[TelemetryTuple]
    ):
        self._put_to_async_queue(
            MultipurposeSensorTelemetryMessage(
                src=self.name,
                dst=self._telemetry_destination,
                about_node_alias_list=list(
                    map(lambda x: x.AboutNode.alias, telemetry_sample_report_list)
                ),
                value_list=list(
                    map(
                        lambda x: self.latest_telemetry_value[x],
                        telemetry_sample_report_list,
                    )
                ),
                telemetry_name_list=list(
                    map(lambda x: x.TelemetryName, telemetry_sample_report_list)
                ),
            )
        )
        for tt in telemetry_sample_report_list:
            self._last_sampled_s[tt] = int(time.time())
            self.last_reported_telemetry_value[tt] = self.latest_telemetry_value[tt]

    def value_exceeds_async_threshold(self, telemetry_tuple: TelemetryTuple) -> bool:
        """This telemetry tuple is supposed to report asynchronously on change, with
        the amount of change required (as a function of the absolute max value) determined
        in the EqConfig.
        """
        telemetry_reporting_config = self.eq_reporting_config[telemetry_tuple]
        last_reported_value = self.last_reported_telemetry_value[telemetry_tuple]
        latest_telemetry_value = self.latest_telemetry_value[telemetry_tuple]
        abs_telemetry_delta = abs(latest_telemetry_value - last_reported_value)
        max_telemetry_value = self.nameplate_telemetry_value[telemetry_tuple]
        change_ratio = abs_telemetry_delta / max_telemetry_value
        if change_ratio > telemetry_reporting_config.AsyncReportThreshold:
            return True
        return False

    def should_report_telemetry_reading(self, telemetry_tuple: TelemetryTuple) -> bool:
        """The telemetry data should get reported synchronously once every SamplePeriodS, and also asynchronously
        on a big enough change - both configured in the eq_config (eq for electrical quantity) config for this
        telemetry tuple.

        Note that SamplePeriodS will often be 300 seconds, which will also match the duration of each status message
        the Scada sends up to the cloud (GtShSimpleStatus.ReportingPeriodS).  The Scada will likely do this at the
        top of every 5 minutes - but not the power meter.. The point of the synchronous reporting is to
        get at least one reading for this telemetry tuple in the Scada's status report; it does not need to be
        at the beginning or end of the status report time period.
        """
        if self.latest_telemetry_value[telemetry_tuple] is None:
            return False
        if (
            self._last_sampled_s[telemetry_tuple] is None
            or self.last_reported_telemetry_value[telemetry_tuple] is None
        ):
            return True
        if (
            time.time() - self._last_sampled_s[telemetry_tuple]
            > self.eq_reporting_config[telemetry_tuple].SamplePeriodS
        ):
            return True
        if self.value_exceeds_async_threshold(telemetry_tuple):
            return True
        return False

    @property
    def latest_agg_power_w(self) -> Optional[int]:
        """Tracks the sum of the power of the all the nodes whose power is getting measured by the power meter"""
        latest_power_list = [
            v
            for k, v in self.latest_telemetry_value.items()
            if k in self._hardware_layout.all_power_tuples
        ]
        if None in latest_power_list:
            return None
        return int(sum(latest_power_list))

    @property
    def nameplate_agg_power_w(self) -> int:
        nameplate_power_list = [
            v
            for k, v in self.nameplate_telemetry_value.items()
            if k in self._hardware_layout.all_power_tuples
        ]
        return int(sum(nameplate_power_list))

    def report_aggregated_power_w(self):
        self._put_to_async_queue(
            GsPwrMessage(
                src=self.name,
                dst=self._telemetry_destination,
                power=self.latest_agg_power_w,
            )
        )
        self.last_reported_agg_power_w = self.latest_agg_power_w

    def should_report_aggregated_power(self) -> bool:
        """Aggregated power is sent up asynchronously on change via a GsPwr message, and the last aggregated
        power sent up is recorded in self.last_reported_agg_power_w."""
        if self.latest_agg_power_w is None:
            return False
        if self.last_reported_agg_power_w is None:
            return True
        abs_power_delta = abs(self.latest_agg_power_w - self.last_reported_agg_power_w)
        change_ratio = abs_power_delta / self.nameplate_agg_power_w
        if change_ratio > self.async_power_reporting_threshold:
            return True
        return False


class PowerMeter(SyncThreadActor):
    def __init__(
        self,
        node: ShNode,
        services: ScadaInterface,
        settings: Optional[ScadaSettings] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):

        super().__init__(
            node=node,
            services=services,
            sync_thread=PowerMeterDriverThread(
                node=node,
                settings=services.settings if settings is None else settings,
                hardware_layout=services.hardware_layout,
                telemetry_destination=services.name,
                channel=SyncAsyncQueueWriter(
                    loop=loop if loop is not None else asyncio.get_event_loop(),
                    async_queue=services.async_receive_queue,
                ),
            ),
        )

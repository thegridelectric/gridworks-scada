from gwproactor.logger import LoggerOrAdapter

from actors.scada_interface import ScadaInterface
from actors.config import ScadaSettings
from gwproactor import SyncThreadActor
from gwproto.data_classes.components.electric_meter_component import ElectricMeterComponent
from gwproto.data_classes.hardware_layout import HardwareLayout
from gwproto.data_classes.sh_node import ShNode
from drivers.power_meter.egauge_4030__power_meter_driver import EGuage4030_PowerMeterDriver
from drivers.power_meter.gridworks_sim_pm1__power_meter_driver import (
    GridworksSimPm1_PowerMeterDriver,
)
from drivers.power_meter.power_meter_driver import PowerMeterDriver
from gwproto.enums import MakeModel


class DriverThreadFactory:
    """A helper class to isolate code only used in construction of PowerMeterDriverThread"""

    FASTEST_POWER_METER_POLL_PERIOD_MS = 40
    DEFAULT_ASYNC_REPORTING_THRESHOLD = 0.05

    node: ShNode
    settings: ScadaSettings
    hardware_layout: HardwareLayout
    component: ElectricMeterComponent
    logger: LoggerOrAdapter

    @classmethod
    def create(
        cls,
        node_name: str,
        services: ScadaInterface,
    ) -> PowerMeterDriver:
        layout = services.hardware_layout
        node = layout.node(node_name)
        if node is None:
            raise ValueError(f"ERROR PowerMeter node {node_name} not found")
        if not isinstance(node.component, ElectricMeterComponent):
            raise ValueError(
                "ERROR. PowerMeterDriverThread requires node with ElectricMeterComponent. "
                f"Received node {node.Name} with component type {type(node.component)}"
            )
        if node.component.cac.MakeModel == MakeModel.GRIDWORKS__SIMPM1:
            return GridworksSimPm1_PowerMeterDriver(node, services)
        elif node.component.cac.MakeModel == MakeModel.EGAUGE__4030:
            return EGuage4030_PowerMeterDriver(node, services)
        raise NotImplementedError(
            f"No ElectricMeter driver yet for {node.component.cac.MakeModel}"
        )

class PowerMeter(SyncThreadActor):

    def __init__(
        self,
        name: str,
        services: ScadaInterface,
    ):
        super().__init__(
            name=name,
            services=services,
            sync_thread=DriverThreadFactory.create(name, services)
            # sync_thread=PowerMeterDriverThread(
            #     node=services.hardware_layout.node(name),
            #     settings=settings,
            #     hardware_layout=services.hardware_layout,
            #     telemetry_destination=services.name,
            #     logger=services.logger.add_category_logger(
            #         self.POWER_METER_LOGGER_NAME,
            #         level=settings.power_meter_logging_level,
            #     )
            # ),
        )


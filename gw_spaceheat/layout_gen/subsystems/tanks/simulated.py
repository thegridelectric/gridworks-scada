from gwsproto.enums import MakeModel, Unit
from gwsproto.named_types import (ChannelConfig, ComponentAttributeClassGt,
                                  SimPicoTankModuleComponentGt)
from layout_gen.core.layout_db import LayoutDb
from layout_gen.subsystems.tanks.config import TankCfg, TanksConfig
from layout_gen.subsystems.tanks.tank_module3 import TankModule3Implementation
from layout_gen.subsystems.tanks.tanks import add_tanks


class SimTankModule3Implementation(TankModule3Implementation):
    """
    Simulated implementation of TankModule3.

    Overrides device and component creation (SimPicoTankModuleComponentGt)
    """

    def _ensure_device(self, db: LayoutDb) -> str:
        alias = MakeModel.GRIDWORKS__SIMMULTITEMP

        cac_id = db.cac_id_by_alias(alias)
        if cac_id:
            return cac_id

        device_id = db.make_cac_id(make_model=alias)

        db.add_cacs([
            ComponentAttributeClassGt(
                ComponentAttributeClassId=device_id,
                DisplayName="GridWorks Simulated MultiTemp sensor",
                MakeModel=alias,
            )
        ])

        return device_id

    def _ensure_component(
        self,
        db: LayoutDb,
        cfg: TankCfg,
        nodes,
        channels,
        device_id: str,
    ) -> str:

        display_name = f"{nodes.reader} SimTankModule"

        existing = db.component_id_by_alias(display_name)
        if existing:
            return existing

        component_id = db.make_component_id(display_name)

        config_list: list[ChannelConfig] = []

        # device temperature channels
        for ch in channels.devices:
            config_list.append(
                ChannelConfig(
                    ChannelName=ch,
                    CapturePeriodS=cfg.ops.capture_period_s,
                    AsyncCapture=True,
                    Exponent=3,
                    Unit=Unit.Celcius,
                )
            )

        # optional microvolt channels
        if cfg.ops.send_micro_volts:
            for ch in channels.electrical:
                config_list.append(
                    ChannelConfig(
                        ChannelName=ch,
                        CapturePeriodS=cfg.ops.capture_period_s,
                        AsyncCapture=True,
                        Exponent=6,
                        Unit=Unit.VoltsRms,
                    )
                )

        db.add_components([
            SimPicoTankModuleComponentGt(
                ComponentId=component_id,
                ComponentAttributeClassId=device_id,
                DisplayName=display_name,
                SerialNumber=cfg.id.serial_number,
                PicoHwUid=cfg.id.pico_hw_uid,
                ConfigList=config_list,
                Enabled=cfg.ops.enabled,
                SendMicroVolts=cfg.ops.send_micro_volts,
                Samples=cfg.ops.samples,
                NumSampleAverages=cfg.ops.num_sample_averages,
                TempCalcMethod=cfg.ops.temp_calc,
                ThermistorBeta=cfg.ops.thermistor_beta,
                AsyncCaptureDeltaMicroVolts=cfg.ops.async_capture_delta_micro_volts,
                SensorOrder=cfg.id.sensor_order,
            )
        ])

        return component_id


def add_simulated_tanks(
    db: LayoutDb,
    *,
    cfgs: TanksConfig,
) -> None:
    """
    Add simulated tanks using the same topology and channel structure
    as real tanks, but with simulated components.
    """
    implementation = SimTankModule3Implementation()

    add_tanks(
        db,
        implementation=implementation,
        cfgs=cfgs,
    )
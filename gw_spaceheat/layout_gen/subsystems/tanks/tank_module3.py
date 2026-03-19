from gwsproto.enums import ActorClass, MakeModel, TelemetryName, Unit
from gwsproto.named_types import (ChannelConfig, ComponentAttributeClassGt,
                                  DataChannelGt, PicoTankModuleComponentGt,
                                  SpaceheatNodeGt)
from gwsproto.names.core.node_names import CoreNodeNames as CNN
from gwsproto.names.hydronic_spaceheat.helpers import (BufferChannelNames,
                                                       BufferNodeNames,
                                                       TankChannelNames,
                                                       TankNodeNames)
from gwsproto.property_format import UUID4Str
from layout_gen.core import LayoutDb
from layout_gen.core.derived_channels import add_temperature_channel
from layout_gen.subsystems.tanks.calibration import TankCalibration
from layout_gen.subsystems.tanks.config import TankCfg


class TankModule3Implementation:
    def add_tank(
            self,
            db: LayoutDb,
            *,
            nodes: TankNodeNames | BufferNodeNames,
            channels: TankChannelNames | BufferChannelNames,
            cfg: TankCfg,
    ) -> None:
        device_id = self._ensure_device(db)
        component_id = self._ensure_component(
            db, cfg, nodes, channels, device_id
        )
        self._add_nodes(db, nodes, component_id)
        self._add_data_channels(db, nodes, channels)
        self._add_derived_channels(db, channels, cfg.cal)

    def _ensure_device(self, db: LayoutDb) -> UUID4Str:
        alias = MakeModel.GRIDWORKS__TANKMODULE3

        cac_id = db.cac_id_by_alias(alias)
        if cac_id:
            return cac_id

        cac_id = db.make_cac_id(make_model=alias)

        db.add_cacs([
            ComponentAttributeClassGt(
                ComponentAttributeClassId=cac_id,
                DisplayName="GridWorks TankModule3 (Uses 1 pico)",
                MakeModel=alias,
            )
        ])

        return cac_id

    def _ensure_component(self, 
                          db: LayoutDb, 
                          cfg: TankCfg, 
                          nodes: TankNodeNames | BufferNodeNames,
                          channels: TankChannelNames | BufferChannelNames, 
                          device_id: UUID4Str) -> str:
        display_name = f"{nodes.reader} PicoTankModule"

        existing = db.component_id_by_alias(display_name)
        if existing:
            return existing

        config_list = []

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

        component_id = db.make_component_id(display_name)

        db.add_components([
            PicoTankModuleComponentGt(
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

    def _add_nodes(self,
                    db: LayoutDb, 
                    nodes: TankNodeNames | BufferNodeNames, 
                    component_id: UUID4Str):
        db.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(nodes.reader),
                    Name=nodes.reader,
                    ActorHierarchyName=f"{CNN.primary_scada}.{nodes.reader}",
                    ActorClass=ActorClass.ApiTankModule,
                    DisplayName=f"{nodes.reader.capitalize()} Tank",
                    ComponentId=component_id,
                )
            ]
            + [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(depth),
                    Name=depth,
                    ActorClass=ActorClass.NoActor,
                    DisplayName=depth,
                )
                for depth in nodes.depths
            ]
        )

    def _add_data_channels(self, 
                           db: LayoutDb, 
                           nodes: TankNodeNames | BufferNodeNames,
                           channels: TankChannelNames | BufferChannelNames):
        depth_nodes = sorted(nodes.depths)

        device_channels = sorted(channels.devices)

        db.add_data_channels(
            [
                DataChannelGt(
                    Name=ch,
                    DisplayName=f"{nodes.reader.capitalize()} Depth {i+1} Device Temp",
                    AboutNodeName=depth_nodes[i],
                    CapturedByNodeName=nodes.reader,
                    TelemetryName=TelemetryName.WaterTempCTimes1000,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(ch),
                )
                for i, ch in enumerate(device_channels)
            ]
        )


        if channels.electrical:
            electrical_channels = sorted(channels.electrical)

            db.add_data_channels(
                [
                    DataChannelGt(
                        Name=ch,
                        DisplayName=f"{nodes.reader.capitalize()} Depth {i+1} MicroVolts",
                        AboutNodeName=depth_nodes[i],
                        CapturedByNodeName=nodes.reader,
                        TelemetryName=TelemetryName.MicroVolts,
                        TerminalAssetAlias=db.terminal_asset_alias,
                        Id=db.make_channel_id(ch),
                    )
                    for i, ch in enumerate(electrical_channels)
                ]
            )

    def _add_derived_channels(self,
                              db: LayoutDb,
                              channels: TankChannelNames | BufferChannelNames,
                              calibration: TankCalibration
                              ):

        for i, effective in enumerate(sorted(channels.effective), start=1):
            add_temperature_channel(
                db,
                node_name=CNN.derived_generator,
                channel_name=effective,
                input_channel=channels.effective_to_device(effective),
                calibration=calibration.calibration_for_depth(i),
            )
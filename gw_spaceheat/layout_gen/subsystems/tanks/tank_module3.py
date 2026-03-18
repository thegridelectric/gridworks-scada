from gwsproto.named_types import PicoTankModuleComponentGt

from layout_gen.core import LayoutDb
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.data_channel_gt import DataChannelGt


from gwsproto.enums import MakeModel, Unit, ActorClass, TelemetryName
from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.names.hydronic_spaceheat.helpers import (
 BufferChannelNames, BufferNodeNames, Tanks, TankNodeNames, TankChannelNames, 
)


from layout_gen.subsystems.tanks.config import TankCfg


class TankModule3Implementation:
    def add_tank(
            self,
            db: LayoutDb,
            *,
            nodes: TankNodeNames | BufferNodeNames,
            channels: TankChannelNames | BufferChannelNames,
            cfg: TankCfg
    ) -> None:
        if not db.cac_id_by_alias(MakeModel.GRIDWORKS__TANKMODULE3):
            db.add_cacs(
                [
                    ComponentAttributeClassGt(
                        ComponentAttributeClassId=db.make_cac_id(make_model=MakeModel.GRIDWORKS__TANKMODULE3),
                        DisplayName="GridWorks TankModule3 (Uses 1 pico)",
                        MakeModel=MakeModel.GRIDWORKS__TANKMODULE3,
                    ),
                ]
            )
        
        if not db.component_id_by_alias(cfg.component_display_name()):
            config_list = []
            for i in range(1,4):
                config_list.append(
                    ChannelConfig(
                        ChannelName=f"{cfg.ActorNodeName}-depth{i}-device",
                        CapturePeriodS=cfg.CapturePeriodS,
                        AsyncCapture=True,
                        Exponent=3,
                        Unit=Unit.Celcius
                    )
                )
            if cfg.SendMicroVolts:
                for i in range(1,4):
                    config_list.append(
                        ChannelConfig(
                            ChannelName=f"{cfg.ActorNodeName}-depth{i}-micro-v",
                            CapturePeriodS=cfg.CapturePeriodS,
                            AsyncCapture=True,
                            Exponent=6,
                            Unit=Unit.VoltsRms
                        )
                    )

            cac_id = db.cac_id_by_alias(MakeModel.GRIDWORKS__TANKMODULE3)
            if not cac_id:
                    raise Exception("NOPE THAT DOES NOT MAKE SENSE")
            db.add_components(
                [
                    PicoTankModuleComponentGt(
                        ComponentId=db.make_component_id(cfg.component_display_name()),
                        ComponentAttributeClassId=cac_id,
                        DisplayName=cfg.component_display_name(),
                        SerialNumber=cfg.SerialNumber,
                        ConfigList=config_list,
                        PicoHwUid=cfg.PicoHwUid,
                        Enabled=cfg.Enabled,
                        SendMicroVolts=cfg.SendMicroVolts,
                        Samples=cfg.Samples,
                        NumSampleAverages=cfg.NumSampleAverages,
                        TempCalcMethod=cfg.TempCalc,
                        ThermistorBeta=cfg.ThermistorBeta,
                        AsyncCaptureDeltaMicroVolts=cfg.AsyncCaptureDeltaMicroVolts,
                        SensorOrder=cfg.SensorOrder,
                    ),
                ]
            )

            db.add_nodes(
                [
                    SpaceheatNodeGt(
                        ShNodeId=db.make_node_id(cfg.ActorNodeName),
                        Name=cfg.ActorNodeName,
                        ActorHierarchyName=f"{H0N.primary_scada}.{cfg.ActorNodeName}",
                        ActorClass=ActorClass.ApiTankModule,
                        DisplayName=f"{cfg.ActorNodeName.capitalize()} Tank",
                        ComponentId=db.component_id_by_alias(cfg.component_display_name())
                    )
                ] + [
                    SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(f"{cfg.ActorNodeName}-depth{i}"),
                    Name=f"{cfg.ActorNodeName}-depth{i}",
                    ActorClass=ActorClass.NoActor,
                    DisplayName=f"{cfg.ActorNodeName}-depth{i}",
                    )
                    for i in  range(1,4)
                ]
            )

            db.add_data_channels(
                [ DataChannelGt(
                Name=f"{cfg.ActorNodeName}-depth{i}-device",
                DisplayName=f"{cfg.ActorNodeName.capitalize()} Depth {i} Device Temp",
                AboutNodeName=f"{cfg.ActorNodeName}-depth{i}",
                CapturedByNodeName=cfg.ActorNodeName,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id=db.make_channel_id(f"{cfg.ActorNodeName}-depth{i}-device")
                ) for i in range(1,4)
                ]
            )

            if cfg.SendMicroVolts:
                db.add_data_channels(
                    [ DataChannelGt(
                        Name=f"{cfg.ActorNodeName}-depth{i}-micro-v",
                        DisplayName=f"{cfg.ActorNodeName.capitalize()} Depth {i} MicroVolts",
                        AboutNodeName=f"{cfg.ActorNodeName}-depth{i}",
                        CapturedByNodeName=cfg.ActorNodeName,
                        TelemetryName=TelemetryName.MicroVolts,
                        TerminalAssetAlias=db.terminal_asset_alias,
                        Id=db.make_channel_id(f"{cfg.ActorNodeName}-depth{i}-micro-v")
                    ) for i in range(1,4)
                    ]
                )
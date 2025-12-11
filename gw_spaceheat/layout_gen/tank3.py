from gwproto.named_types import PicoTankModuleComponentGt
from typing import cast, Optional
from pydantic import BaseModel
from gwproto.property_format import SpaceheatName
from layout_gen import LayoutDb
from gwproto.named_types import ComponentGt
from gwproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwproto.named_types.data_channel_gt import DataChannelGt
from gwproto.enums import MakeModel, Unit, ActorClass, TelemetryName
from gwproto.named_types.channel_config import ChannelConfig
from gwproto.named_types import SpaceheatNodeGt
from gwsproto.data_classes.house_0_names import H0N
from gwproto.enums import TempCalcMethod

class Tank3Cfg(BaseModel):
    SerialNumber: str
    PicoHwUid: str
    ActorNodeName: SpaceheatName = "buffer"
    CapturePeriodS: int = 60
    AsyncCaptureDeltaMicroVolts: int = 2000
    Samples:int  = 1000
    NumSampleAverages:int = 30
    Enabled: bool = True
    SendMicroVolts: bool = True
    TempCalc: TempCalcMethod = TempCalcMethod.SimpleBeta
    ThermistorBeta: int = 3977 # Beta for the Amphenols
    SensorOrder: list[int] = [1,2,3]
    
    def component_display_name(self) -> str:
        return f"{self.ActorNodeName} PicoTankModule"


def add_tank3(
        db: LayoutDb,
        tank_cfg: Tank3Cfg
) -> None:
    if not db.cac_id_by_alias(MakeModel.GRIDWORKS__TANKMODULE3):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(MakeModel.GRIDWORKS__TANKMODULE3),
                    DisplayName="GridWorks TankModule3 (Uses 1 pico)",
                    MakeModel=MakeModel.GRIDWORKS__TANKMODULE3,
                ),
            ]
        )
    
    if not db.component_id_by_alias(tank_cfg.component_display_name()):
        config_list = []
        for i in range(1,4):
            config_list.append(
                ChannelConfig(
                    ChannelName=f"{tank_cfg.ActorNodeName}-depth{i}",
                    CapturePeriodS=tank_cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=3,
                    Unit=Unit.Celcius
                )
            )
        if tank_cfg.SendMicroVolts:
            for i in range(1,4):
                config_list.append(
                    ChannelConfig(
                        ChannelName=f"{tank_cfg.ActorNodeName}-depth{i}-micro-v",
                        CapturePeriodS=tank_cfg.CapturePeriodS,
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
                    ComponentId=db.make_component_id(tank_cfg.component_display_name()),
                    ComponentAttributeClassId=cac_id,
                    DisplayName=tank_cfg.component_display_name(),
                    SerialNumber=tank_cfg.SerialNumber,
                    ConfigList=config_list,
                    PicoHwUid=tank_cfg.PicoHwUid,
                    Enabled=tank_cfg.Enabled,
                    SendMicroVolts=tank_cfg.SendMicroVolts,
                    Samples=tank_cfg.Samples,
                    NumSampleAverages=tank_cfg.NumSampleAverages,
                    TempCalcMethod=tank_cfg.TempCalc,
                    ThermistorBeta=tank_cfg.ThermistorBeta,
                    AsyncCaptureDeltaMicroVolts=tank_cfg.AsyncCaptureDeltaMicroVolts,
                    SensorOrder=tank_cfg.SensorOrder,
                ),
            ]
        )

        db.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(tank_cfg.ActorNodeName),
                    Name=tank_cfg.ActorNodeName,
                    ActorHierarchyName=f"{H0N.primary_scada}.{tank_cfg.ActorNodeName}",
                    ActorClass=ActorClass.ApiTankModule,
                    DisplayName=f"{tank_cfg.ActorNodeName.capitalize()} Tank",
                    ComponentId=db.component_id_by_alias(tank_cfg.component_display_name())
                )
            ] + [
                SpaceheatNodeGt(
                ShNodeId=db.make_node_id(f"{tank_cfg.ActorNodeName}-depth{i}"),
                Name=f"{tank_cfg.ActorNodeName}-depth{i}",
                ActorClass=ActorClass.NoActor,
                DisplayName=f"{tank_cfg.ActorNodeName}-depth{i}",
                )
                for i in  range(1,4)
            ]
        )

        db.add_data_channels(
            [ DataChannelGt(
               Name=f"{tank_cfg.ActorNodeName}-depth{i}",
               DisplayName=f"{tank_cfg.ActorNodeName.capitalize()} Depth {i}",
               AboutNodeName=f"{tank_cfg.ActorNodeName}-depth{i}",
               CapturedByNodeName=tank_cfg.ActorNodeName,
               TelemetryName=TelemetryName.WaterTempCTimes1000,
               TerminalAssetAlias=db.terminal_asset_alias,
               Id=db.make_channel_id(f"{tank_cfg.ActorNodeName}-depth{i}")
               ) for i in range(1,4)
            ]
        )

        if tank_cfg.SendMicroVolts:
            db.add_data_channels(
                [ DataChannelGt(
                    Name=f"{tank_cfg.ActorNodeName}-depth{i}-micro-v",
                    DisplayName=f"{tank_cfg.ActorNodeName.capitalize()} Depth {i} MicroVolts",
                    AboutNodeName=f"{tank_cfg.ActorNodeName}-depth{i}",
                    CapturedByNodeName=tank_cfg.ActorNodeName,
                    TelemetryName=TelemetryName.MicroVolts,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(f"{tank_cfg.ActorNodeName}-depth{i}-micro-v")
                ) for i in range(1,4)
                ]
            )
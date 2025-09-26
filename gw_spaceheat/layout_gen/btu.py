from gwproto.named_types import PicoBtuMeterComponentGt
from typing import Optional, Any
from pydantic import BaseModel
from gwproto.property_format import SpaceheatName
from layout_gen import LayoutDb
from gwproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwproto.named_types.data_channel_gt import DataChannelGt
from gwproto.enums import MakeModel, Unit, ActorClass, TelemetryName
from gwproto.enums import  TempCalcMethod as EnumTempCalcMethod
from gwproto.named_types.channel_config import ChannelConfig
from gwproto.named_types import SpaceheatNodeGt
from gwsproto.data_classes.house_0_names import H0N
from gwproto.enums import GpmFromHzMethod, HzCalcMethod


SAIER_CONSTANT_GALLONS_PER_TICK = 0.0009

class BtuCfg(BaseModel):
    Enabled: bool = True
    SerialNumber: str = "NA"
    HwUid: Optional[str] = None
    ActorNodeName: SpaceheatName
    FlowNodeName: SpaceheatName
    HotNodeName: SpaceheatName
    ColdNodeName: SpaceheatName
    ReadCt: bool
    CtNodeName: Optional[SpaceheatName] = None
    FlowMeterType: MakeModel = MakeModel.SAIER__SENHZG1WA
    HzMethod: HzCalcMethod = HzCalcMethod.UniformWindow
    GpmMethod: GpmFromHzMethod = GpmFromHzMethod.Constant
    TempCalcMethod: EnumTempCalcMethod = EnumTempCalcMethod.SimpleBeta
    ThermistorBeta: int = 3977
    CapturePeriodS: int = 300
    AsyncCaptureDeltaGpmX100: int = 10
    AsyncCaptureDeltaCelsiusX100: int = 20
    AsyncCaptureDeltaCtVoltsX100: Optional[int] = None 
    GallonsPerPulse: float = SAIER_CONSTANT_GALLONS_PER_TICK

    def component_display_name(self) -> str:
        return f"{self.ActorNodeName} BtuMeter"
    

def add_btu(
        db: LayoutDb,
        cfg: BtuCfg
) -> None:
    if not cfg.FlowMeterType == MakeModel.SAIER__SENHZG1WA:
        raise Exception("Only designed for SAIER SEN RIGHT NOW")

    if not db.cac_id_by_alias(MakeModel.GRIDWORKS__GW101):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(MakeModel.GRIDWORKS__GW101),
                    DisplayName="Pico BtuMeter1 Gw101",
                    MakeModel=MakeModel.GRIDWORKS__GW101,
                ),
            ]
        )

    if not db.component_id_by_alias(cfg.component_display_name()):
        config_list = [
                ChannelConfig(
                    ChannelName=f"{cfg.FlowNodeName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=2,
                    Unit=Unit.Gpm
                ),
                ChannelConfig(
                    ChannelName=f"{cfg.HotNodeName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=2,
                    Unit=Unit.Celcius
                ),
                ChannelConfig(
                    ChannelName=f"{cfg.ColdNodeName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=2,
                    Unit=Unit.Celcius
                ),
        ]
        if cfg.ReadCt:
            config_list.append(
                ChannelConfig(
                    ChannelName=f"{cfg.CtNodeName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=2,
                    Unit=Unit.VoltsRms
                )
            )

        cac_id = db.cac_id_by_alias(MakeModel.GRIDWORKS__GW101)
        if not cac_id:
            raise Exception("NOPE THAT DOES NOT MAKE SENSE")
        
        db.add_components(
            [
                PicoBtuMeterComponentGt(
                    ComponentId=db.make_component_id(cfg.component_display_name()),
                    ComponentAttributeClassId=cac_id,
                    HwUid=cfg.HwUid,
                    DisplayName=cfg.component_display_name(),
                    ConfigList=config_list,
                    Enabled=cfg.Enabled,
                    SerialNumber=cfg.SerialNumber,
                    FlowNodeName=cfg.FlowNodeName,
                    HotNodeName=cfg.HotNodeName,
                    ColdNodeName=cfg.ColdNodeName,
                    ReadCt=cfg.ReadCt,
                    CtNodeName=cfg.CtNodeName,
                    FlowMeterType=cfg.FlowMeterType,
                    HzCalcMethod=cfg.HzMethod,
                    TempCalcMethod=cfg.TempCalcMethod,
                    ThermistorBeta=cfg.ThermistorBeta,
                    GpmFromHzMethod=cfg.GpmMethod,
                    GallonsPerPulse=cfg.GallonsPerPulse,
                    AsyncCaptureDeltaGpmX100=cfg.AsyncCaptureDeltaGpmX100,
                    AsyncCaptureDeltaCelsiusX100=cfg.AsyncCaptureDeltaCelsiusX100,
                    AsyncCaptureDeltaCtVoltsX100=cfg.AsyncCaptureDeltaCtVoltsX100,
                )
            ]
        )

        nodes_to_add = [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(cfg.ActorNodeName),
                Name=cfg.ActorNodeName,
                ActorHierarchyName=f"{H0N.primary_scada}.{cfg.ActorNodeName}",
                ActorClass=ActorClass.ApiBtuMeter,
                DisplayName=f"{cfg.ActorNodeName.replace('-', ' ').title()}",
                ComponentId=db.component_id_by_alias(cfg.component_display_name())
            )
        ]
        

        # Add AboutNodes for flow, hot, and cold (if they don't already exist)
        for node_name in [cfg.FlowNodeName, cfg.HotNodeName, cfg.ColdNodeName]:
                nodes_to_add.append(
                    SpaceheatNodeGt(
                        ShNodeId=db.make_node_id(node_name),
                        Name=node_name,
                        ActorClass=ActorClass.NoActor,
                        DisplayName=node_name.replace('-', ' ').title(),
                    )
                )

        # Add CT AboutNode if configured
        if cfg.ReadCt and cfg.CtNodeName:
            nodes_to_add.append(
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(cfg.CtNodeName),
                    Name=cfg.CtNodeName,
                    ActorClass=ActorClass.NoActor,
                    DisplayName=cfg.CtNodeName.replace('-', ' ').title(),
                )
            )

        db.add_nodes(nodes_to_add)

        ### DATA CHANNELS

        db.add_data_channels(
            [ 
                DataChannelGt(
                    Name=cfg.FlowNodeName,
                    DisplayName=f"{cfg.FlowNodeName.replace('-', ' ').title()} Gpm X 100",
                    AboutNodeName=cfg.FlowNodeName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.GpmTimes100,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.FlowNodeName)
                ),
                DataChannelGt(
                    Name=cfg.HotNodeName,
                    DisplayName=f"{cfg.HotNodeName.replace('-', ' ').title()} Celsius X 1000",
                    AboutNodeName=cfg.HotNodeName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.WaterTempCTimes1000,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.HotNodeName)
                ),
                DataChannelGt(
                    Name=cfg.ColdNodeName,
                    DisplayName=f"{cfg.ColdNodeName.replace('-', ' ').title()} Celsius X 1000",
                    AboutNodeName=cfg.ColdNodeName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.WaterTempCTimes1000,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.ColdNodeName)
                ),
            ]
        )
        if cfg.CtNodeName:
            db.add_data_channels(
                [
                    DataChannelGt(
                    Name=cfg.CtNodeName,
                    DisplayName=f"{cfg.CtNodeName.replace('-', ' ').title()} Volts x 100",
                    AboutNodeName=cfg.CtNodeName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.VoltsTimes100,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.CtNodeName)
                ),
                ]
            )


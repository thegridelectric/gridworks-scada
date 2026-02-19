from typing import Optional, Any
from pydantic import BaseModel
from gwsproto.property_format import SpaceheatName

from gwsproto.enums import MakeModel, Unit, ActorClass, TelemetryName
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import GpmFromHzMethod, HzCalcMethod
from gwsproto.named_types import (
    ChannelConfig, ComponentAttributeClassGt, DataChannelGt, 
    PicoFlowModuleComponentGt, SpaceheatNodeGt,
)
from layout_gen import LayoutDb


SAIER_CONSTANT_GALLONS_PER_TICK = 0.0009
EKM_CONSTANT_GALLONS_PER_TICK = 0.0748

class HallCfg(BaseModel):
    Enabled: bool = True
    SerialNumber: str = "NA"
    HwUid: Optional[str] = None
    ActorNodeName: SpaceheatName = H0N.dist_flow
    FlowNodeName: Optional[SpaceheatName] = None
    FlowMeterType: MakeModel = MakeModel.SAIER__SENHZG1WA
    HzMethod: HzCalcMethod = HzCalcMethod.BasicExpWeightedAvg
    GpmMethod: GpmFromHzMethod = GpmFromHzMethod.Constant
    CapturePeriodS: int = 300
    AsyncCaptureThresholdGpmTimes100: int = 20
    SendHz: bool = True
    SendTickLists: bool = False
    ConstantGallonsPerTick: float = SAIER_CONSTANT_GALLONS_PER_TICK
    SendHz: bool = True
    NoFlowMs: int = 250
    PublishEmptyTicklistAfterS: int = 7
    PublishTicklistPeriodS: int = 10 
    ExpAlpha: Optional[float] = 0.2
    CutoffFrequency: Optional[float] = None

    def component_display_name(self) -> str:
        return f"{self.ActorNodeName} HallFlowModule"
    
class ReedCfg(BaseModel):
    Enabled: bool = True
    SerialNumber: str = "NA"
    HwUid: Optional[str] = None
    ActorNodeName: SpaceheatName = H0N.dist_flow
    FlowNodeName: Optional[SpaceheatName] = None
    FlowMeterType: MakeModel = MakeModel.EKM__HOTSPWM075HD
    HzMethod: HzCalcMethod = HzCalcMethod.BasicExpWeightedAvg
    GpmMethod: GpmFromHzMethod = GpmFromHzMethod.Constant
    CapturePeriodS: int = 300
    AsyncCaptureThresholdGpmTimes100: int = 5
    SendHz: bool = True
    SendTickLists: bool = False
    ConstantGallonsPerTick: float = EKM_CONSTANT_GALLONS_PER_TICK
    NoFlowMs: int = 5000
    PublishAnyTicklistAfterS: int = 10
    PublishTicklistLength: int = 10 
    ExpAlpha: Optional[float] = 0.5
    CutoffFrequency: Optional[float] = None

    def component_display_name(self) -> str:
        return f"{self.ActorNodeName.replace('-', ' ').title()} ReedFlowModule"


def add_flow(
        db: LayoutDb,
        flow_cfg: Any
) -> None:
    if flow_cfg.FlowNodeName is None:
        flow_cfg.FlowNodeName = flow_cfg.ActorNodeName
    flow_reed_cfg: ReedCfg = flow_cfg
    flow_hall_cfg: HallCfg = flow_cfg
    if type(flow_cfg) is HallCfg:
        is_hall = True
        make_model = MakeModel.GRIDWORKS__PICOFLOWHALL
        cac_display_name = "Pico Flow Hall"
    else:
        is_hall = False
        make_model = MakeModel.GRIDWORKS__PICOFLOWREED
        cac_display_name = "Pico Flow Reed"
    if not db.cac_id_by_alias(make_model):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(make_model=make_model),
                    DisplayName=cac_display_name,
                    MakeModel=make_model,
                ),
            ]
        )

    
    if not db.component_id_by_alias(flow_cfg.component_display_name):
        config_list = [
                ChannelConfig(
                    ChannelName=f"{flow_cfg.FlowNodeName}",
                    CapturePeriodS=flow_cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=2,
                    Unit=Unit.Gpm
                )
        ]
        if flow_cfg.SendHz:
            config_list.append(
                ChannelConfig(
                    ChannelName=f"{flow_cfg.FlowNodeName}-hz",
                    CapturePeriodS=flow_cfg.CapturePeriodS,
                    AsyncCapture=True,
                    Exponent=6,
                    Unit=Unit.VoltsRms
                )
            )
        if is_hall:
            db.add_components(
                [
                    PicoFlowModuleComponentGt(
                        ComponentId=db.make_component_id(flow_hall_cfg.component_display_name),
                        ComponentAttributeClassId=db.cac_id_by_alias(make_model),
                        DisplayName=flow_hall_cfg.component_display_name(),
                        ConfigList=config_list,
                        HwUid=flow_hall_cfg.HwUid,
                        Enabled = flow_hall_cfg.Enabled,
                        SerialNumber=flow_hall_cfg.SerialNumber,            
                        FlowNodeName=flow_hall_cfg.FlowNodeName,
                        HzCalcMethod=flow_hall_cfg.HzMethod,
                        GpmFromHzMethod=flow_hall_cfg.GpmMethod,
                        ConstantGallonsPerTick=flow_hall_cfg.ConstantGallonsPerTick,
                        SendHz=flow_hall_cfg.SendHz,
                        SendGallons=False,
                        SendTickLists=flow_hall_cfg.SendTickLists,
                        NoFlowMs=flow_hall_cfg.NoFlowMs,
                        PublishEmptyTicklistAfterS=flow_hall_cfg.PublishEmptyTicklistAfterS,
                        AsyncCaptureThresholdGpmTimes100=flow_hall_cfg.AsyncCaptureThresholdGpmTimes100,
                        PublishTicklistPeriodS=flow_hall_cfg.PublishTicklistPeriodS,
                        ExpAlpha=flow_hall_cfg.ExpAlpha,
                    ),
                ]
            )
        else:
            db.add_components(
                [
                    PicoFlowModuleComponentGt(
                        ComponentId=db.make_component_id(flow_reed_cfg.component_display_name),
                        ComponentAttributeClassId=db.cac_id_by_alias(make_model),
                        DisplayName=flow_reed_cfg.component_display_name(),
                        ConfigList=config_list,
                        Enabled = flow_reed_cfg.Enabled,
                        SerialNumber=flow_reed_cfg.SerialNumber,            
                        HwUid=flow_reed_cfg.HwUid,
                        FlowNodeName=flow_reed_cfg.FlowNodeName,
                        FlowMeterType=flow_reed_cfg.FlowMeterType,
                        HzCalcMethod=flow_reed_cfg.HzMethod,
                        GpmFromHzMethod=flow_reed_cfg.GpmMethod,
                        ConstantGallonsPerTick=flow_reed_cfg.ConstantGallonsPerTick,
                        SendHz=flow_reed_cfg.SendHz,
                        SendGallons=False,
                        SendTickLists=flow_reed_cfg.SendTickLists,
                        NoFlowMs=flow_reed_cfg.NoFlowMs,
                        PublishAnyTicklistAfterS=flow_reed_cfg.PublishAnyTicklistAfterS,
                        AsyncCaptureThresholdGpmTimes100=flow_reed_cfg.AsyncCaptureThresholdGpmTimes100,
                        PublishTicklistLength=flow_reed_cfg.PublishTicklistLength,
                        ExpAlpha=flow_reed_cfg.ExpAlpha,
                    ),
                ]
            )
        db.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(flow_cfg.ActorNodeName),
                    Name=flow_cfg.ActorNodeName,
                    ActorHierarchyName=f"{H0N.primary_scada}.{flow_cfg.ActorNodeName}",
                    ActorClass=ActorClass.ApiFlowModule,
                    DisplayName=f"{flow_cfg.ActorNodeName.replace('-', ' ').title()}",
                    ComponentId=db.component_id_by_alias(flow_cfg.component_display_name())
                ),
            ] 
        )

        db.add_data_channels(
            [ DataChannelGt(
               Name=flow_cfg.ActorNodeName,
               DisplayName=f"{flow_cfg.ActorNodeName.replace('-', ' ').title()} Gpm X 100",
               AboutNodeName=flow_cfg.FlowNodeName,
               CapturedByNodeName=flow_cfg.ActorNodeName,
               TelemetryName=TelemetryName.GpmTimes100,
               TerminalAssetAlias=db.terminal_asset_alias,
               Id=db.make_channel_id(flow_cfg.ActorNodeName)
            )
            ]
        )

        if flow_cfg.SendHz:
            db.add_data_channels(
                [ DataChannelGt(
                    Name=f"{flow_cfg.ActorNodeName}-hz",
                    DisplayName=f"{flow_cfg.ActorNodeName.replace('-', ' ').title()} MicroHz",
                    AboutNodeName=flow_cfg.ActorNodeName,
                    CapturedByNodeName=flow_cfg.ActorNodeName,
                    TelemetryName=TelemetryName.MicroHz,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(f"{flow_cfg.ActorNodeName}-hz")
                )
                ]
            )
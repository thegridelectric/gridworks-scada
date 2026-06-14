from gwsproto.named_types import PicoBtuMeterComponentGt
from typing import Optional, Any
from typing_extensions import Self
from pydantic import BaseModel, model_validator
from gwsproto.property_format import SpaceheatName
from layout_gen import LayoutDb
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.enums import Gw1DeviceType, Unit, ActorClass, TelemetryName
from gwsproto.enums import  TempCalcMethod as EnumTempCalcMethod
from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import GpmFromHzMethod, HzCalcMethod, GwQuantity


SAIER_CONSTANT_GALLONS_PER_TICK = 0.0009

class BtuCfg(BaseModel):
    Enabled: bool = True
    SerialNumber: str = "NA"
    HwUid: Optional[str] = None
    ActorNodeName: SpaceheatName
    FlowChannelName: SpaceheatName
    SendHz: bool = False
    HotChannelName: SpaceheatName
    ColdChannelName: SpaceheatName
    ReadCtVoltage: bool
    CtChannelName: Optional[SpaceheatName] = None
    FlowMeterType: str = Gw1DeviceType.SaierFlowSensor
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

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ReadCtVoltage is True iff AsyncCaptureDeltaCtVoltsX100 exists
        """
        if self.ReadCtVoltage and not self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(f"Axiom 1 violated! ReadCtVoltage {self.ReadCtVoltage} requires AsyncCaptureDeltaCtVoltsX100!")
        if not self.ReadCtVoltage and self.AsyncCaptureDeltaCtVoltsX100:
            raise ValueError(f"Axiom 1 violated: ReadCtVoltage {self.ReadCtVoltage} means NO AsyncCaptureDeltaCtVoltsX100. Got {self.AsyncCaptureDeltaCtVoltsX100}")
        return self


def add_btu(
        db: LayoutDb,
        cfg: BtuCfg
) -> None:
    if not cfg.FlowMeterType == Gw1DeviceType.SaierFlowSensor:
        raise Exception("Only designed for SAIER SEN RIGHT NOW")

    if not db.has_device_type_record(Gw1DeviceType.GridworksGw101):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    DeviceType=Gw1DeviceType.GridworksGw101,
                    DisplayName="Pico BtuMeter1 Gw101",
                ),
            ]
        )

    if not db.component_id_by_alias(cfg.component_display_name()):
        config_list = [
                ChannelConfig(
                    ChannelName=f"{cfg.FlowChannelName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    AsyncCaptureDelta=cfg.AsyncCaptureDeltaGpmX100,
                    Exponent=2,
                    Unit=Unit.Gpm
                ),
                ChannelConfig(
                    ChannelName=f"{cfg.HotChannelName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    AsyncCaptureDelta=cfg.AsyncCaptureDeltaCelsiusX100,
                    Exponent=2,
                    Unit=Unit.Celcius
                ),
                ChannelConfig(
                    ChannelName=f"{cfg.ColdChannelName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    AsyncCaptureDelta=cfg.AsyncCaptureDeltaCelsiusX100,
                    Exponent=2,
                    Unit=Unit.Celcius
                ),
        ]
        if cfg.ReadCtVoltage:
            config_list.append(
                ChannelConfig(
                    ChannelName=f"{cfg.CtChannelName}",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    AsyncCaptureDelta=cfg.AsyncCaptureDeltaCtVoltsX100,
                    Exponent=2,
                    Unit=Unit.VoltsRms
                )
            )

        db.add_components(
            [
                PicoBtuMeterComponentGt(
                    ComponentId=db.make_component_id(cfg.component_display_name()),
                    DeviceType=Gw1DeviceType.GridworksGw101,
                    HwUid=cfg.HwUid,
                    DisplayName=cfg.component_display_name(),
                    ConfigList=config_list,
                    Enabled=cfg.Enabled,
                    SerialNumber=cfg.SerialNumber,
                    FlowChannelName=cfg.FlowChannelName,
                    SendHz=cfg.SendHz,
                    HotChannelName=cfg.HotChannelName,
                    ColdChannelName=cfg.ColdChannelName,
                    ReadCtVoltage=cfg.ReadCtVoltage,
                    CtChannelName=cfg.CtChannelName,
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
        for node_name in [cfg.FlowChannelName, cfg.HotChannelName, cfg.ColdChannelName]:
                nodes_to_add.append(
                    SpaceheatNodeGt(
                        ShNodeId=db.make_node_id(node_name),
                        Name=node_name,
                        ActorClass=ActorClass.NoActor,
                        DisplayName=node_name.replace('-', ' ').title(),
                    )
                )

        # Add CT AboutNode if configured
        if cfg.ReadCtVoltage and cfg.CtChannelName:
            nodes_to_add.append(
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(cfg.CtChannelName),
                    Name=cfg.CtChannelName,
                    ActorClass=ActorClass.NoActor,
                    DisplayName=cfg.CtChannelName.replace('-', ' ').title(),
                )
            )

        db.add_nodes(nodes_to_add)

        ### DATA CHANNELS

        db.add_data_channels(
            [
                DataChannelGt(
                    Name=cfg.FlowChannelName,
                    DisplayName=f"{cfg.FlowChannelName.replace('-', ' ').title()} Gpm X 100",
                    AboutNodeName=cfg.FlowChannelName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.GpmTimes100,
                    Quantity=GwQuantity.FlowRate,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.FlowChannelName)
                ),
                DataChannelGt(
                    Name=cfg.HotChannelName,
                    DisplayName=f"{cfg.HotChannelName.replace('-', ' ').title()} Celsius X 1000",
                    AboutNodeName=cfg.HotChannelName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.WaterTempCTimes1000,
                    Quantity=GwQuantity.Temperature,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.HotChannelName)
                ),
                DataChannelGt(
                    Name=cfg.ColdChannelName,
                    DisplayName=f"{cfg.ColdChannelName.replace('-', ' ').title()} Celsius X 1000",
                    AboutNodeName=cfg.ColdChannelName,
                    CapturedByNodeName=cfg.ActorNodeName,
                    TelemetryName=TelemetryName.WaterTempCTimes1000,
                    Quantity=GwQuantity.Temperature,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(cfg.ColdChannelName)
                ),
            ]
        )
        if cfg.CtChannelName:
            db.add_data_channels(
                [
                    DataChannelGt(
                        Name=cfg.CtChannelName,
                        DisplayName=f"{cfg.CtChannelName.replace('-', ' ').title()} Volts x 100",
                        AboutNodeName=cfg.CtChannelName,
                        CapturedByNodeName=cfg.ActorNodeName,
                        TelemetryName=TelemetryName.VoltsTimes100,
                        Quantity=GwQuantity.Voltage,
                        TerminalAssetAlias=db.terminal_asset_alias,
                        Id=db.make_channel_id(cfg.CtChannelName)
                    ),
                ]
            )

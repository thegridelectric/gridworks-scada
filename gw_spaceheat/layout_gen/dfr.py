from gwsproto.data_classes.house_0_names import H0CN, H0N
from gwsproto.enums import ActorClass, MakeModel, TelemetryName, Unit
from gwsproto.named_types import (
    DataChannelGt,
    DfrComponentGt,
    DfrConfig,
    SpaceheatNodeGt,
)
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from pydantic import BaseModel
from layout_gen import LayoutDb

component_display_name = "DFRobot 010V output X 2"

class DfrConf(BaseModel):
    DistPumpDefault: int = 30
    PrimaryPumpDefault: int = 50
    StorePumpDefault: int = 50

def add_dfrs(db: LayoutDb, dfr_config: DfrConf) -> None:
    if not db.cac_id_by_alias(MakeModel.DFROBOT__DFR0971_TIMES2):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(
                        MakeModel.DFROBOT__DFR0971_TIMES2
                    ),
                    DisplayName="DFRobot DFR0971 X 2",
                    MakeModel=MakeModel.DFROBOT__DFR0971_TIMES2
                ),
            ]
        )

    if not db.component_id_by_alias(component_display_name):
        config_list = [
            DfrConfig(
                ChannelName=H0CN.dist_010v,
                CapturePeriodS=300,
                AsyncCapture=True,
                Exponent=1,
                Unit=Unit.VoltsRms,
                OutputIdx=1,
                InitialVoltsTimes100=dfr_config.DistPumpDefault,
            ),
            DfrConfig(
                ChannelName=H0CN.primary_010v,
                CapturePeriodS=300,
                AsyncCapture=True,
                Exponent=1,
                Unit=Unit.VoltsRms,
                OutputIdx=2,
                InitialVoltsTimes100=dfr_config.PrimaryPumpDefault,
            ),
            DfrConfig(
                ChannelName=H0CN.store_010v,
                CapturePeriodS=300,
                AsyncCapture=True,
                Exponent=1,
                Unit=Unit.VoltsRms,
                OutputIdx=3,
                InitialVoltsTimes100=dfr_config.StorePumpDefault,
            ),
        ]

        db.add_components(
            [
                DfrComponentGt(
                    ComponentId=db.make_component_id(component_display_name),
                    ComponentAttributeClassId=db.cac_id_by_alias(
                        MakeModel.DFROBOT__DFR0971_TIMES2
                    ),
                    DisplayName=component_display_name,
                    ConfigList=config_list,
                    I2cAddressList=[94, 95],  # 0x5e, 0x5f
                )
            ]
        )

    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.zero_ten_out_multiplexer),
                Name=H0N.zero_ten_out_multiplexer,
                ActorHierarchyName=f"{H0N.primary_scada}.{H0N.zero_ten_out_multiplexer}",
                ActorClass=ActorClass.I2cDfrMultiplexer,
                DisplayName="I2c Zero Ten Out Multiplexer",
                ComponentId=db.component_id_by_alias(component_display_name),
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.dist_010v),
                Name=H0N.dist_010v,
                ActorHierarchyName=f"{H0N.primary_scada}.{H0N.dist_010v}",
                Handle=f"auto.{H0N.dist_010v}",
                ActorClass=ActorClass.ZeroTenOutputer,
                DisplayName="Dist DFR",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.primary_010v),
                Name=H0N.primary_010v,
                ActorHierarchyName=f"{H0N.primary_scada}.{H0N.primary_010v}",
                Handle=f"auto.{H0N.primary_010v}",
                ActorClass=ActorClass.ZeroTenOutputer,
                DisplayName="Primary DFR",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.store_010v),
                Name=H0N.store_010v,
                ActorHierarchyName=f"{H0N.primary_scada}.{H0N.store_010v}",
                Handle=f"auto.{H0N.store_010v}",
                ActorClass=ActorClass.ZeroTenOutputer,
                DisplayName="Store DFR",
            ),
        ]
    )

    db.add_data_channels( [
        DataChannelGt(
            Name=H0CN.dist_010v,
            DisplayName="Dist 010V",
            AboutNodeName=H0N.dist_010v,
            CapturedByNodeName=H0N.zero_ten_out_multiplexer,
            TelemetryName=TelemetryName.VoltsTimesTen,
            TerminalAssetAlias=db.terminal_asset_alias,
            Id=db.make_channel_id(H0CN.dist_010v),
        ),
        DataChannelGt(
            Name=H0CN.primary_010v,
            DisplayName="Primary 010V",
            AboutNodeName=H0N.primary_010v,
            CapturedByNodeName=H0N.zero_ten_out_multiplexer,
            TelemetryName=TelemetryName.VoltsTimesTen,
            TerminalAssetAlias=db.terminal_asset_alias,
            Id=db.make_channel_id(H0CN.primary_010v),
        ),
        DataChannelGt(
            Name=H0CN.store_010v,
            DisplayName="Store 010V",
            AboutNodeName=H0N.store_010v,
            CapturedByNodeName=H0N.zero_ten_out_multiplexer,
            TelemetryName=TelemetryName.VoltsTimesTen,
            TerminalAssetAlias=db.terminal_asset_alias,
            Id=db.make_channel_id(H0CN.store_010v),
        ),
    ]
    )

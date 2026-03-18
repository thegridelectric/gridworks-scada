import typing
from gwsproto.enums import (
    ActorClass,
    MakeModel,
    TelemetryName,
)
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL
from gwsproto.named_types import (
    ComponentAttributeClassGt,
    ComponentGt,
    DataChannelGt,
    ElectricMeterCacGt,
    ElectricMeterChannelConfig,
    SpaceheatNodeGt,
)

from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt

def add_stub_power_meter(self, cfg: Optional[StubConfig] = None):
    if cfg is None:
        cfg = StubConfig()
    if MakeModel.GRIDWORKS__SIMPM1 not in self.maps.cacs_by_alias:
        self.add_cacs(
            [
                typing.cast(
                    ComponentAttributeClassGt,
                    ElectricMeterCacGt(
                        ComponentAttributeClassId=CACS_BY_MAKE_MODEL[MakeModel.GRIDWORKS__SIMPM1],
                        MakeModel=MakeModel.GRIDWORKS__SIMPM1,
                        DisplayName=cfg.power_meter_cac_alias,
                        TelemetryNameList=[TelemetryName.PowerW],
                        MinPollPeriodMs=1000,
                    )
                ),
            ],
            "ElectricMeterCacs"
        )
    
    self.add_components(
        [
            typing.cast(
                ComponentGt,
                ElectricMeterComponentGt(
                    ComponentId=self.make_component_id(cfg.power_meter_component_alias),
                    ComponentAttributeClassId=self.cac_id_by_alias(MakeModel.GRIDWORKS__SIMPM1),
                    DisplayName=cfg.power_meter_component_alias,
                    ConfigList=[
                        ElectricMeterChannelConfig(
                            ChannelName=H0CN.hp_odu_pwr,
                            PollPeriodMs=1000,
                            CapturePeriodS=300,
                            AsyncCapture=True,
                            AsyncCaptureDelta=200,
                            Exponent=0,
                            Unit=Unit.W,
                        ),
                        ElectricMeterChannelConfig(
                            ChannelName=H0CN.hp_idu_pwr,
                            PollPeriodMs=1000,
                            CapturePeriodS=300,
                            AsyncCapture=True,
                            AsyncCaptureDelta=200,
                            Exponent=0,
                            Unit=Unit.W,
                        ),
                    ],
                )
            )
        ],
        "ElectricMeterComponents"
    )
    self.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=self.make_node_id(H0N.primary_power_meter),
                Name=H0N.primary_power_meter,
                ActorClass=ActorClass.PowerMeter,
                DisplayName=cfg.power_meter_node_display_name,
                ComponentId=self.component_id_by_alias(cfg.power_meter_component_alias),
            ),
            SpaceheatNodeGt(
                ShNodeId=self.make_node_id(H0N.hp_odu),
                Name=H0N.hp_odu,
                ActorClass=ActorClass.NoActor,
                DisplayName=cfg.boost_element_display_name,
                InPowerMetering=True,
                NameplatePowerW=4500,
            ),
            SpaceheatNodeGt(
                ShNodeId=self.make_node_id(H0N.hp_idu),
                Name=H0N.hp_idu,
                ActorClass=ActorClass.NoActor,
                DisplayName=cfg.boost_element_display_name,
                InPowerMetering=True,
                NameplatePowerW=4500,
            ),
        ]
    )
    
    self.add_data_channels(
        [
            DataChannelGt(
                Name=H0CN.hp_odu_pwr,
                Id=self.make_channel_id(H0CN.hp_odu_pwr),
                DisplayName=' '.join(word.capitalize() for word in H0CN.hp_odu_pwr.split('-')) + " Pwr",
                AboutNodeName=H0N.hp_odu,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
                TerminalAssetAlias=self.terminal_asset_alias
            ),
            DataChannelGt(
                Name=H0CN.hp_idu_pwr,
                Id=self.make_channel_id(H0CN.hp_idu_pwr),
                DisplayName=' '.join(word.capitalize() for word in H0CN.hp_idu_pwr.split('-')) + " Pwr",
                AboutNodeName=H0N.hp_idu,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
                TerminalAssetAlias=self.terminal_asset_alias
            )
        ]
    )
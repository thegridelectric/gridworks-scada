from typing import cast, Optional
from pydantic import BaseModel

from gwsproto.type_helpers import CACS_BY_MAKE_MODEL
from gwsproto.enums import ActorClass
from gwsproto.enums import MakeModel
from gwsproto.enums import TelemetryName 
from gwsproto.enums import Unit
from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.named_types import ComponentGt
from gwsproto.named_types import EgaugeRegisterConfig
from gwsproto.named_types import ElectricMeterCacGt
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.named_types import ElectricMeterChannelConfig
from gwsproto.named_types import DataChannelGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt


from gwsproto.data_classes.house_0_names import H0N
from layout_gen.layout_db import LayoutDb


class EgaugeChannelConfig(BaseModel):
    AboutNodeName: str
    EGaugeAddress: int
    NameplatePowerW: int = 10
    AsyncCaptureDelta: int = 2
    AsyncCapture: bool = True
    InPowerMetering: bool = False

    @property
    def ChannelName(self) -> str:
        return f"{self.AboutNodeName}-pwr"

    def node(self, db: LayoutDb) -> SpaceheatNodeGt:
        return SpaceheatNodeGt(
            ShNodeId=db.make_node_id(self.AboutNodeName),
            Name=self.AboutNodeName,
            ActorClass=ActorClass.NoActor,
            DisplayName=' '.join(word.capitalize() for word in self.AboutNodeName.split('-')),
            InPowerMetering=self.InPowerMetering,
            NameplatePowerW=self.NameplatePowerW
        )

    def channel_config(self, **kwargs) -> ElectricMeterChannelConfig:
        kwargs_used = dict(
            ChannelName=f"{self.AboutNodeName}-pwr",
            PollPeriodMs = 1000,
            CapturePeriodS=300,
            AsyncCapture=self.AsyncCapture,
            AsyncCaptureDelta=self.AsyncCaptureDelta,
            Exponent=0,
            Unit=Unit.W,
            EgaugeRegisterConfig=EgaugeRegisterConfig(
                                    Address=self.EGaugeAddress,
                                    Name=self.AboutNodeName,
                                    Description="change in value",
                                    Type="f32",
                                    Denominator=1,
                                    Unit=Unit.W
                )
        )
        kwargs_used.update(kwargs)
        return ElectricMeterChannelConfig(**kwargs_used)

#assumes for now it is an egauge
class PowerMeterGenConfig(BaseModel):
    NodeName: str = H0N.primary_power_meter
    NodeDisplayName: str = "Primary Power Meter"
    ComponentDisplayName: str = "EGauge Power Meter"
    HwUid: str
    ModbusHost: str
    ModbusPort: int = 502
    CapturePeriodS: int = 60
    PollPeriodMs: int = 1000
    ChannelConfigs: list[EgaugeChannelConfig]

    def channel_configs(
        self,
        kwargs: Optional[dict] = None,
    ) -> list[EgaugeChannelConfig]:
        if kwargs is None:
            kwargs = {}
        kwargs["CapturePeriodS"] = self.CapturePeriodS
        kwargs["PollPeriodMs"] = self.PollPeriodMs
        return [
            ch.channel_config(kwargs=kwargs)
            for ch in self.ChannelConfigs
        ]

def add_egauge(
    db: LayoutDb,
    egauge: PowerMeterGenConfig,
) -> None:
    make_model = MakeModel.EGAUGE__4030
    if not db.cac_id_by_alias(make_model):
        db.add_cacs(
            [
                cast(
                    ComponentAttributeClassGt,
                    ElectricMeterCacGt(
                        ComponentAttributeClassId=CACS_BY_MAKE_MODEL[make_model],
                        MakeModel=make_model,
                        MinPollPeriodMs=1000,
                        DisplayName="EGauge 4030",
                        TelemetryNameList=[TelemetryName.PowerW],
                    )
                )
            ],
            "ElectricMeterCacs",
        )
    db.add_components(
        [
            cast(
                ComponentGt,
                ElectricMeterComponentGt(
                    ComponentId=db.make_component_id(egauge.ComponentDisplayName),
                    ComponentAttributeClassId=db.cac_id_by_alias(make_model),
                    DisplayName=egauge.ComponentDisplayName,
                    ConfigList=egauge.channel_configs(),
                    HwUid=egauge.HwUid,
                    ModbusHost=egauge.ModbusHost,
                    ModbusPort=egauge.ModbusPort,
                )
            )
        ],
        "ElectricMeterComponents",
    )
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(egauge.NodeName),
                Name=egauge.NodeName,
                ActorClass=ActorClass.PowerMeter,
                ActorHierarchyName=f"{H0N.primary_scada}.{egauge.NodeName}",
                DisplayName=egauge.NodeDisplayName,
                ComponentId=db.component_id_by_alias(egauge.ComponentDisplayName),
            )
        ] + [
            SpaceheatNodeGt(
            ShNodeId=db.make_node_id(cfg.AboutNodeName),
            Name=cfg.AboutNodeName,
            ActorClass=ActorClass.NoActor,
            DisplayName=' '.join(word.capitalize() for word in cfg.AboutNodeName.split('-')),
            InPowerMetering=cfg.InPowerMetering,
            NameplatePowerW=cfg.NameplatePowerW
        )
            for cfg in egauge.ChannelConfigs if not db.node_id_by_name(cfg.AboutNodeName)]
    )
    db.add_data_channels(
        [
            DataChannelGt(
                Name=cfg.ChannelName,
                DisplayName=' '.join(part.upper() for part in cfg.ChannelName.split('-')),
                Id=db.make_channel_id(cfg.ChannelName),
                AboutNodeName=cfg.AboutNodeName,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=cfg.InPowerMetering,
                TerminalAssetAlias=db.terminal_asset_alias,
            )
            for cfg in egauge.ChannelConfigs
        ]
    )

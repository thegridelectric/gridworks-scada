from typing import cast

from typing import Optional

from gwsproto.enums import ActorClass
from gwsproto.enums import MakeModel
from gwsproto.enums import TelemetryName
from gwsproto.enums import Unit
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL
from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.named_types import ComponentGt
from gwsproto.named_types import Ads111xBasedCacGt
from gwsproto.named_types import SpaceheatNodeGt
from gwsproto.named_types import  AdsChannelConfig
from gwsproto.named_types import DataChannelGt
from gwsproto.named_types.ads111x_based_component_gt import Ads111xBasedComponentGt
from gwsproto.enums import ThermistorDataMethod
from pydantic import BaseModel
from gwsproto.data_classes.house_0_names import H0N
from layout_gen.layout_db import LayoutDb

class SensorNodeGenCfg(BaseModel):
    ChannelName: str
    AboutNodeName: Optional[str] = None
    TerminalBlockIdx: int
    AsyncCapture: bool = True
    CapturePeriodS: int = 300
    ThermistorMakeModel: MakeModel = MakeModel.TEWA__TT0P10KC3T1051500
    # Using a forward reference here resolves a pydantic exception generated when this field
    # is actually set, as in tlayouts/gen_oak.py. I don't know why we should need a forward
    # reference, since TelemetryName is imported above. The generated error is:
    #
    # pydantic.errors.ConfigError: field "TelemetryName" not yet prepared so
    #   type is still a ForwardRef, you might need to call
    #   SensorNodeGenCfg.update_forward_refs().
    AsyncCaptureDelta: int = 500
    MyTelemetryName: TelemetryName = TelemetryName.WaterTempCTimes1000

    def about_node_name(self) -> str:
        if self.AboutNodeName:
            return self.AboutNodeName
        else:
            return self.ChannelName

class TSnapMultipurposeGenCfg(BaseModel):
    HWUid: str
    SensorCfgs: list[SensorNodeGenCfg]
    OpenVoltageByAds: list[float] = [5.0, 5.0, 5.0]

    def component_alias(self) -> str:
        return f"Multipurpose Temp Sensor <{self.HWUid}>"

def add_tsnap_multipurpose(
    db: LayoutDb,
    tsnap: TSnapMultipurposeGenCfg,
) -> None:
    make_model = MakeModel.GRIDWORKS__TSNAP1
    if not db.cac_id_by_alias(make_model):
        db.add_cacs(
            [
                cast(
                    ComponentAttributeClassGt,
                    Ads111xBasedCacGt(
                        ComponentAttributeClassId=CACS_BY_MAKE_MODEL[make_model],
                        MakeModel=make_model,
                        AdsI2cAddressList= [0x4b, 0x49, 0x48],
                        TelemetryNameList=[TelemetryName.WaterTempCTimes1000, TelemetryName.AirTempCTimes1000],
                        TotalTerminalBlocks=12,
                        MinPollPeriodMs=200,
                        DisplayName="GridWorks TSnap1.0 as 12-channel analog temp sensor",
                    )
                )
            ],
            "Ads111xBasedCacs",
        )
    
    db.add_components(
        [
            cast(
                ComponentGt,
                Ads111xBasedComponentGt(
                    ComponentId=db.make_component_id(tsnap.component_alias()),
                    ComponentAttributeClassId=db.cac_id_by_alias(make_model),
                    ConfigList=[
                        AdsChannelConfig(
                            ChannelName=sensor_cfg.ChannelName,
                            CapturePeriodS=sensor_cfg.CapturePeriodS,
                            AsyncCapture=sensor_cfg.AsyncCapture,
                            AsyncCaptureDelta=sensor_cfg.AsyncCaptureDelta,
                            Exponent=3,
                            Unit=Unit.Celcius,
                            TerminalBlockIdx=sensor_cfg.TerminalBlockIdx,
                            ThermistorMakeModel=sensor_cfg.ThermistorMakeModel,
                            DataProcessingMethod=ThermistorDataMethod.BetaWithExponentialAveraging,
                        )
                        for sensor_cfg in tsnap.SensorCfgs
                    ],
                    OpenVoltageByAds=tsnap.OpenVoltageByAds,
                    DisplayName=tsnap.component_alias(),
                    HwUid=tsnap.HWUid
                )
            )
        ],
        "Ads111xBasedComponents",
    )
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.analog_temp),
                Name=H0N.analog_temp,
                ActorHierarchyName=f"{H0N.secondary_scada}.{H0N.analog_temp}",
                ActorClass=ActorClass.MultipurposeSensor,
                DisplayName=' '.join(part.upper() for part in H0N.analog_temp.split('-')),
                ComponentId=db.component_id_by_alias(tsnap.component_alias())
            )
        ] + [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(cfg.about_node_name()),
                Name=cfg.about_node_name(), 
                ActorClass=ActorClass.NoActor,
                DisplayName=' '.join(part.upper() for part in cfg.about_node_name().split('-')),
            )
            for cfg in tsnap.SensorCfgs if not db.node_id_by_name(cfg.about_node_name())
        ]
    )
    db.add_data_channels(
        [
            DataChannelGt(
                Name=cfg.ChannelName,
                DisplayName=' '.join(part.upper() for part in cfg.ChannelName.split('-')),
                Id=db.make_channel_id(cfg.ChannelName),
                AboutNodeName=cfg.about_node_name(),
                CapturedByNodeName=H0N.analog_temp,
                TelemetryName=cfg.MyTelemetryName,
                TerminalAssetAlias=db.terminal_asset_alias,
            )

            for cfg in tsnap.SensorCfgs
        ]

    )

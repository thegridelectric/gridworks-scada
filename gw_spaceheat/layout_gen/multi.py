from typing import cast

from typing import Optional

from gwproto.enums import ActorClass
from gwproto.enums import MakeModel
from gwproto.enums import Role
from gwproto.enums import TelemetryName
from gwproto.enums import Unit
from gwproto.type_helpers import CACS_BY_MAKE_MODEL
from gwproto.types import ComponentAttributeClassGt
from gwproto.types import ComponentGt
from gwproto.types import Ads111xBasedCacGt
from gwproto.types import SpaceheatNodeGt
from gwproto.types import  AdsChannelConfig
from gwproto.types import DataChannelGt
from gwproto.types.ads111x_based_component_gt import Ads111xBasedComponentGt
from gwproto.enums import ThermistorDataMethod, MakeModel
from pydantic import BaseModel
from data_classes.house_0 import H0Readers

from layout_gen.layout_db import LayoutDb

class SensorNodeGenCfg(BaseModel):
    ChannelName: str
    AboutNodeName: Optional[str] = None
    TerminalBlockIdx: int
    AsyncCapture: bool = True
    CapturePeriodS: int = 60
    ThermistorMakeModel: MakeModel = MakeModel.TEWA__TT0P10KC3T1051500
    # Using a forward reference here resolves a pydantic exception generated when this field
    # is actually set, as in tlayouts/gen_oak.py. I don't know why we should need a forward
    # reference, since TelemetryName is imported above. The generated error is:
    #
    # pydantic.errors.ConfigError: field "TelemetryName" not yet prepared so
    #   type is still a ForwardRef, you might need to call
    #   SensorNodeGenCfg.update_forward_refs().
    AsyncCaptureDelta: int = 200
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
                        AdsI2cAddressList= ["0x4b", "0x48", "0x49"],
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
                            PollPeriodMs=200,
                            CapturePeriodS=sensor_cfg.CapturePeriodS,
                            AsyncCapture=sensor_cfg.AsyncCapture,
                            AsyncCaptureDelta=sensor_cfg.AsyncCaptureDelta,
                            Exponent=3,
                            Unit=Unit.Celcius,
                            TerminalBlockIdx=sensor_cfg.TerminalBlockIdx,
                            ThermistorMakeModel=sensor_cfg.ThermistorMakeModel,
                            DataProcessingMethod=ThermistorDataMethod.SimpleBeta,
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
                ShNodeId=db.make_node_id(H0Readers.analog_temp),
                Alias=H0Readers.analog_temp,
                ActorClass=ActorClass.MultipurposeSensor,
                Role=Role.MultiChannelAnalogTempSensor,
                DisplayName=' '.join(part.upper() for part in H0Readers.analog_temp.split('-')),
                ComponentId=db.component_id_by_alias(tsnap.component_alias())
            )
        ] + [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(cfg.about_node_name()),
                Alias=cfg.about_node_name(), 
                ActorClass=ActorClass.NoActor,
                Role=Role.Unknown,
                DisplayName=' '.join(part.upper() for part in cfg.about_node_name().split('-')),
            )
            for cfg in tsnap.SensorCfgs if not db.node_id_by_alias(cfg.about_node_name())
        ]
    )
    db.add_data_channels(
        [
            DataChannelGt(
                Name=cfg.ChannelName,
                DisplayName=' '.join(part.upper() for part in cfg.ChannelName.split('-')),
                Id=db.make_channel_id(cfg.ChannelName),
                AboutNodeName=cfg.about_node_name(),
                CapturedByNodeName=H0Readers.analog_temp,
                TelemetryName=cfg.MyTelemetryName,
                TerminalAssetAlias=db.terminal_asset_alias,
            )

            for cfg in tsnap.SensorCfgs
        ]

    )

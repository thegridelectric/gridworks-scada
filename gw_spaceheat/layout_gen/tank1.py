# For GRIDWORKS__TANK_MODULE_1, which used IoT Fibaro devices through Hubitat
from typing import Optional
from typing import Tuple

from gwproto.enums import ActorClass
from gwproto.enums import MakeModel
from gwproto.enums import TelemetryName
from gwproto.enums import Unit
from gwproto.type_helpers import CACS_BY_MAKE_MODEL
from gwproto.named_types import ChannelConfig
from gwproto.named_types import ComponentAttributeClassGt
from gwproto.named_types import DataChannelGt
from gwproto.named_types import FibaroSmartImplantComponentGt
from gwproto.type_helpers import FibaroTempSensorSettingsGt
from gwproto.named_types import HubitatComponentGt
from gwproto.named_types import HubitatTankComponentGt
from gwproto.type_helpers import HubitatTankSettingsGt
from gwproto.named_types import SpaceheatNodeGt
from gwproto.named_types.hubitat_gt import HubitatGt
from pydantic import BaseModel

from layout_gen import LayoutDb

class FibaroGenCfg(BaseModel):
    SN: str
    ZWaveDSK: str

    def alias(self) -> str:
        return f"Fibaro Smart Implant {self.SN}"

class Tank1Cfg(BaseModel):
    NodeName: str
    InHomeName: str
    SN: str
    DeviceIds: Tuple[int, int, int, int]
    DefaultPollPeriodSeconds: Optional[float] = None
    DevicePollPeriodSeconds: Tuple[float|None, float|None, float|None, float|None] = None, None, None, None

    def node_display_name(self) -> str:
        return f"Tank Module <{self.InHomeName}>"

    def component_alias(self) -> str:
        return f"Tank Module <{self.InHomeName}>  SN {self.SN}"

    def thermistor_node_name(self, depth: int) -> str:
        return f"{self.NodeName}-depth{depth}"

    def thermistor_node_display_name(self, depth: int) -> str:
        if depth == 1:
            extra = " (top)"
        elif depth == len(self.DeviceIds):
            extra = " (bottom)"
        else:
            extra = ""
        return f"{self.node_display_name()} temp sensor at depth {depth}{extra}"

def add_tank1(
    db: LayoutDb,
    fibaro_a: FibaroGenCfg,
    fibaro_b: FibaroGenCfg,
    hubitat: HubitatGt,
    tank: Tank1Cfg,
) -> None:
    fibaro_make_model = MakeModel.FIBARO__ANALOG_TEMP_SENSOR
    if not db.cac_id_by_alias(fibaro_make_model):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=CACS_BY_MAKE_MODEL[fibaro_make_model],
                    DisplayName="Fibaro SmartImplant FGBS-222",
                    MakeModel=MakeModel.FIBARO__ANALOG_TEMP_SENSOR,
                ),
            ]
        )
    hubitat_make_model = MakeModel.HUBITAT__C7__LAN1
    if not db.cac_id_by_alias(hubitat_make_model):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=CACS_BY_MAKE_MODEL[hubitat_make_model],
                    DisplayName="Hubitat Elevation C-7",
                    MakeModel=MakeModel.HUBITAT__C7__LAN1,
                ),
            ]
        )
    tank_module_make_model = MakeModel.GRIDWORKS__TANK_MODULE_1
    if not db.cac_id_by_alias(tank_module_make_model):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=CACS_BY_MAKE_MODEL[tank_module_make_model],
                    DisplayName="Hubitat Tank Module",
                    MakeModel=MakeModel.GRIDWORKS__TANK_MODULE_1
                ),
            ]
        )

    hubitat_alias = f"Hubitat {hubitat.MacAddress[-8:]}"
    if not db.component_id_by_alias(hubitat_alias):
        db.add_components(
            [
                HubitatComponentGt(
                    ComponentId=db.make_component_id(hubitat_alias),
                    ComponentAttributeClassId=db.cac_id_by_alias(hubitat_make_model),
                    DisplayName=hubitat_alias,
                    Hubitat=hubitat,
                    ConfigList=[],
                ),
            ]
    )
    db.add_components(
        [
            FibaroSmartImplantComponentGt(
                ComponentId=db.make_component_id(fibaro_a.alias()),
                ComponentAttributeClassId=db.cac_id_by_alias(fibaro_make_model),
                DisplayName=fibaro_a.alias(),
                ZWaveDSK=fibaro_a.ZWaveDSK,
                ConfigList=[
                    ChannelConfig(
                        ChannelName=channel_name,
                        PollPeriodMs=1000,
                        CapturePeriodS=10,
                        AsyncCapture=False,
                        Exponent=1,
                        Unit=Unit.Celcius,
                    )
                    for channel_name in [tank.thermistor_node_name(i) for i in range(1, 3)]
                ],
            ),
            FibaroSmartImplantComponentGt(
                ComponentId=db.make_component_id(fibaro_b.alias()),
                ComponentAttributeClassId=db.cac_id_by_alias(fibaro_make_model),
                DisplayName=fibaro_b.alias(),
                ZWaveDSK=fibaro_b.ZWaveDSK,
                ConfigList=[
                    ChannelConfig(
                        ChannelName=channel_name,
                        PollPeriodMs=1000,
                        CapturePeriodS=10,
                        AsyncCapture=False,
                        Exponent=1,
                        Unit=Unit.Celcius,
                    )
                    for channel_name in [tank.thermistor_node_name(i) for i in range(3, 5)]
                ],
            ),
        ]
    )
    db.add_components(
        [
            HubitatTankComponentGt(
                ComponentId=db.make_component_id(tank.component_alias()),
                ComponentAttributeClassId=db.cac_id_by_alias(tank_module_make_model),
                DisplayName=tank.component_alias(),
                ConfigList=[],
                Tank=HubitatTankSettingsGt(
                    hubitat_component_id=db.component_id_by_alias(hubitat_alias),
                    default_poll_period_seconds=tank.DefaultPollPeriodSeconds,
                    devices=[
                        FibaroTempSensorSettingsGt(
                            stack_depth=1,
                            device_id=tank.DeviceIds[0],
                            fibaro_component_id=db.component_id_by_alias(fibaro_a.alias()),
                            analog_input_id=1,
                            tank_label=f"{tank.SN} A1 (Thermistor #1 TANK TOP)",
                            enabled=True,
                            poll_period_seconds=tank.DevicePollPeriodSeconds[0],
                        ),
                        FibaroTempSensorSettingsGt(
                            stack_depth=2,
                            device_id=tank.DeviceIds[1],
                            fibaro_component_id=db.component_id_by_alias(fibaro_a.alias()),
                            analog_input_id=2,
                            tank_label=f"{tank.SN} A2 (Thermistor #2)",
                            enabled=True,
                            poll_period_seconds=tank.DevicePollPeriodSeconds[1],
                        ),
                        FibaroTempSensorSettingsGt(
                            stack_depth=3,
                            device_id=tank.DeviceIds[2],
                            fibaro_component_id=db.component_id_by_alias(fibaro_b.alias()),
                            analog_input_id=1,
                            tank_label=f"{tank.SN} B1 (Thermistor #3)",
                            enabled=True,
                            poll_period_seconds=tank.DevicePollPeriodSeconds[2],
                        ),
                        FibaroTempSensorSettingsGt(
                            stack_depth=4,
                            device_id=tank.DeviceIds[3],
                            fibaro_component_id=db.component_id_by_alias(fibaro_b.alias()),
                            analog_input_id=2,
                            tank_label=f"{tank.SN} B2 (Thermistor #4 TANK BOTTOM)",
                            enabled=True,
                            poll_period_seconds=tank.DevicePollPeriodSeconds[3],
                        ),
                    ]
                ),
            ),
        ]
    )

    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(tank.NodeName),
                Name=tank.NodeName,
                ActorClass=ActorClass.HubitatTankModule,
                DisplayName=tank.node_display_name(),
                ComponentId=db.component_id_by_alias(tank.component_alias())
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(tank.thermistor_node_name(1)),
                Name=tank.thermistor_node_name(1),
                ActorClass=ActorClass.NoActor,
                DisplayName=tank.thermistor_node_display_name(1),
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(tank.thermistor_node_name(2)),
                Name=tank.thermistor_node_name(2),
                ActorClass=ActorClass.NoActor,
                DisplayName=tank.thermistor_node_display_name(2),
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(tank.thermistor_node_name(3)),
                Name=tank.thermistor_node_name(3),
                ActorClass=ActorClass.NoActor,
                DisplayName=tank.thermistor_node_display_name(3),
            ),

            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(tank.thermistor_node_name(4)),
                Name=tank.thermistor_node_name(4),
                ActorClass=ActorClass.NoActor,
                DisplayName=tank.thermistor_node_display_name(4),
            ),
        ]
    )


    db.add_data_channels(
       [
           DataChannelGt(
               Name=thermistor_node_name,
               DisplayName=' '.join(word.capitalize() for word in thermistor_node_name.split('-')),
               AboutNodeName=thermistor_node_name,
               CapturedByNodeName=thermistor_node_name,
               TelemetryName=TelemetryName.WaterTempCTimes1000,
               TerminalAssetAlias=db.terminal_asset_alias,
               Id=db.make_channel_id(thermistor_node_name)
           )
           for thermistor_node_name in [tank.thermistor_node_name(i) for i in range(1, 5)]
       ]
    )


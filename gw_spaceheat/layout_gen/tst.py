import typing
from pathlib import Path

from gwproto.enums import ActorClass
from gwproto.enums import MakeModel
from gwproto.enums import TelemetryName
from gwproto.enums import Unit
from gwproto.type_helpers import HubitatGt
from gwproto.named_types import ComponentAttributeClassGt
from gwproto.named_types import ComponentGt
from gwproto.named_types import ElectricMeterCacGt
from gwproto.named_types import SpaceheatNodeGt
from gwproto.named_types import ElectricMeterChannelConfig
from gwproto.named_types import DataChannelGt
from gwproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from data_classes.house_0_names import H0N, H0CN
from pydantic_extra_types.mac_address import MacAddress

from layout_gen import add_tank2
from layout_gen import LayoutDb
from layout_gen import LayoutIDMap
from layout_gen import StubConfig
from layout_gen import HubitatThermostatGenCfg
from layout_gen import add_thermostat
from layout_gen import Tank2Cfg
from layout_gen.relay import add_relays
from layout_gen.relay import RelayCfg
from layout_gen.synth_channels import add_synth
from layout_gen.synth_channels import SynthConfig


def make_tst_layout(src_path: Path) -> LayoutDb:
    db = LayoutDb(
        existing_layout=LayoutIDMap.from_path(src_path),
        add_stubs=True,
        stub_config=StubConfig(
            atn_gnode_alias="d1.isone.ct.newhaven.orange1",
            scada_display_name="Little Orange House Main Scada",
            zone_list=["main"],
            total_store_tanks=3,
            add_stub_power_meter=False,
        )
    )
    _add_power_meter(db)

    hubitat = HubitatGt(
        Host="192.168.0.1",
        MakerApiId=1,
        AccessToken="64a43fa4-0eb9-478f-ad2e-374bc9b7e51f",
        MacAddress=MacAddress("34:E1:D1:82:22:22"),
    )

    add_thermostat(
        db,
        HubitatThermostatGenCfg(
            zone_idx=1,
            zone_name="main",
            hubitat=hubitat,
            device_id=1,
        )
    )

    add_relays(db, RelayCfg(PollPeriodMs=200, CapturePeriodS=300))

    add_tank2(
        db,
        Tank2Cfg(
            ActorNodeName="buffer",
            SerialNumber="9999",
            PicoAHwUid="pico_aaaaaa",
            PicoBHwUid="pico_bbbbbb",
        ),
    )

    add_synth(
        db,
        SynthConfig(
            Name="usable-energy",
            Strategy="layer-by-layer",
        ),
    )

    add_synth(
        db,
        SynthConfig(
            Name="required-energy",
            Strategy="house-parameters-and-weather",
        ),
    )

    return db


def _add_atn(db: LayoutDb) -> LayoutDb:
    ATN_NODE_NAME = H0N.atn
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(ATN_NODE_NAME),
                Name=ATN_NODE_NAME,
                ActorClass=ActorClass.Atn,
                DisplayName="AtomicTNode",
            ),
        ]
    )
    return db

def _add_power_meter(db: LayoutDb) -> LayoutDb:
    POWER_METER_COMPONENT_DISPLAY_NAME = "Power Meter for Simulated Test system"


    if not db.cac_id_by_alias(MakeModel.GRIDWORKS__SIMPM1):
        db.add_cacs(
            [
                typing.cast(
                    ComponentAttributeClassGt,
                    ElectricMeterCacGt(
                        ComponentAttributeClassId=db.make_cac_id(MakeModel.GRIDWORKS__SIMPM1),
                        MakeModel=MakeModel.GRIDWORKS__SIMPM1,
                        DisplayName="Gridworks Pm1 Simulated Power Meter",
                        TelemetryNameList=[TelemetryName.PowerW],
                        MinPollPeriodMs=1000,
                    )
                ),
            ],
            "ElectricMeterCacs"
        )

    db.add_components(
        [
            typing.cast(
                ComponentGt,
                ElectricMeterComponentGt(
                    ComponentId=db.make_component_id(POWER_METER_COMPONENT_DISPLAY_NAME),
                    ComponentAttributeClassId=db.cac_id_by_alias(MakeModel.GRIDWORKS__SIMPM1),
                    DisplayName=POWER_METER_COMPONENT_DISPLAY_NAME,
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
                        ElectricMeterChannelConfig(
                                ChannelName=H0CN.store_pump_pwr,
                                PollPeriodMs=1000,
                                CapturePeriodS=300,
                                AsyncCapture=True,
                                AsyncCaptureDelta=5,
                                Exponent=0,
                                Unit=Unit.W,
                            )
                    ],
                )
            ),
        ],
        "ElectricMeterComponents"
    )
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.primary_power_meter),
                Name=H0N.primary_power_meter,
                ActorClass=ActorClass.PowerMeter,
                ActorHierarchyName=f"{H0N.primary_scada}.{H0N.primary_power_meter}",
                DisplayName="Main Power Meter Little Orange House Test System",
                ComponentId=db.component_id_by_alias(POWER_METER_COMPONENT_DISPLAY_NAME),
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.hp_odu),
                Name=H0N.hp_odu,
                ActorClass=ActorClass.NoActor,
                DisplayName="HP ODU",
                NameplatePowerW=6000,
                InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.hp_idu),
                Name=H0N.hp_idu,
                ActorClass=ActorClass.NoActor,
                DisplayName="HP IDU",
                NameplatePowerW=4000,
                InPowerMetering=True,
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0N.store_pump),
                Name=H0N.store_pump,
                ActorClass=ActorClass.NoActor,
                DisplayName="Store Pump",
            ),

        ]
    )
    # db.add_data_channels(
    #     [
    #         DataChannelGt(
    #             Name=stub.Name,
    #             DisplayName=' '.join(part.upper() for part in stub.Name.split('-')),
    #             AboutNodeName=stub.AboutNodeName,
    #             CapturedByNodeName=stub.CapturedByNodeName,
    #             TelemetryName=stub.TelemetryName,
    #             InPowerMetering=stub.InPowerMetering,
    #             Id=db.make_channel_id(stub.Name),
    #             TerminalAssetAlias=db.terminal_asset_alias,
    #         )
    #         for stub in ChanneStubDbByName.values()
    #     ]
    # )
    db.add_data_channels(
        [
            DataChannelGt(
                Name=H0CN.hp_odu_pwr,
                DisplayName=' '.join(part.upper() for part in H0CN.hp_odu_pwr.split('-')),
                AboutNodeName=H0N.hp_odu,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
                Id=db.make_channel_id(H0CN.hp_odu_pwr),
                TerminalAssetAlias=db.terminal_asset_alias,
            ),
            DataChannelGt(
                Name=H0CN.hp_idu_pwr,
                DisplayName=' '.join(part.upper() for part in H0CN.hp_idu_pwr.split('-')),
                AboutNodeName=H0N.hp_idu,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=True,
                Id=db.make_channel_id(H0CN.hp_idu_pwr),
                TerminalAssetAlias=db.terminal_asset_alias,
            ),
            DataChannelGt(
                Name=H0CN.store_pump_pwr,
                DisplayName=' '.join(part.upper() for part in H0CN.store_pump_pwr.split('-')),
                AboutNodeName=H0N.store_pump,
                CapturedByNodeName=H0N.primary_power_meter,
                TelemetryName=TelemetryName.PowerW,
                InPowerMetering=False,
                Id=db.make_channel_id(H0CN.store_pump_pwr),
                TerminalAssetAlias=db.terminal_asset_alias,
            ),
            


        ]

    )
    return db



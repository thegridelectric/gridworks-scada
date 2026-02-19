from layout_gen import LayoutDb
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL

from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import MakeModel, Unit, ActorClass, TelemetryName
from gwsproto.named_types import (
    ChannelConfig, ComponentAttributeClassGt,  
    DataChannelGt, SimPicoTankModuleComponentGt, SpaceheatNodeGt,
)


from layout_gen.tank3 import Tank3Cfg, add_tank3

   
def add_simulated_tanks(
    db: LayoutDb,
) -> None:

    if not db.cac_id_by_alias(MakeModel.GRIDWORKS__SIMMULTITEMP):
        db.add_cacs(
            [
                ComponentAttributeClassGt(
                    ComponentAttributeClassId=db.make_cac_id(make_model=MakeModel.GRIDWORKS__SIMMULTITEMP),
                    DisplayName="GridWorks Simulated MultiTemp sensor",
                    MakeModel=MakeModel.GRIDWORKS__SIMMULTITEMP,
                ),
            ]
        )

    # -------------------------------------------------
    # Buffer tank
    # -------------------------------------------------
    add_sim_tank(db, "buffer")

    # # -------------------------------------------------
    # # Storage tanks: tank1 .. tankN
    # # -------------------------------------------------
    # for tank_idx in range(1, db.loaded.total_store_tanks + 1):
    #     reader = f"tank{tank_idx}"
    #     add_sim_tank(db, reader)


def add_sim_tank(db: LayoutDb, reader: str):

    cfg = Tank3Cfg(
        SerialNumber="NA",
        PicoHwUid=f"sim-{reader}-pico",
    )
    display_name = reader.replace("-", " ").title()
    component_id = db.make_component_id(display_name)
    db.add_nodes(
            [
                SpaceheatNodeGt(
                    ShNodeId=db.make_node_id(reader),
                    Name=reader,
                    ActorHierarchyName=f"{H0N.primary_scada}.{reader}",
                    ActorClass=ActorClass.ApiTankModule,
                    DisplayName=f"{display_name} SIMULATED ApiTankModule actor",
                    ComponentId=component_id,
                )
            ] + [
                SpaceheatNodeGt(
                ShNodeId=db.make_node_id(f"{reader}-depth{i}"),
                Name=f"{reader}-depth{i}",
                ActorClass=ActorClass.NoActor,
                DisplayName=f"{reader}-depth{i}",
                )
                for i in  range(1,4)
            ]
        )

    config_list = []
    for i in range(1,4):
        depth_i_channels = [ChannelConfig(
                ChannelName=f"{reader}-depth{i}-device",
                CapturePeriodS=cfg.CapturePeriodS,
                AsyncCapture=True,
                AsyncCaptureDelta=cfg.AsyncCaptureDeltaMicroVolts,
                Exponent=3,
                Unit=Unit.Celcius
            )]
        if cfg.SendMicroVolts:
            depth_i_channels.append( ChannelConfig(
                ChannelName=f"{reader}-depth{i}-micro-v",
                CapturePeriodS=cfg.CapturePeriodS,
                AsyncCapture=True,
                AsyncCaptureDelta=cfg.AsyncCaptureDeltaMicroVolts,
                Exponent=6,
                Unit=Unit.VoltsRms
            ))
        config_list += depth_i_channels

    db.add_components([
            SimPicoTankModuleComponentGt(
            ComponentId=component_id,
            ComponentAttributeClassId=CACS_BY_MAKE_MODEL[MakeModel.GRIDWORKS__SIMMULTITEMP],
            DisplayName=display_name,
            SerialNumber=cfg.SerialNumber,
            ConfigList=config_list,
            PicoHwUid=cfg.PicoHwUid,
            Enabled=cfg.Enabled,
            SendMicroVolts=cfg.SendMicroVolts,
            Samples=cfg.Samples,
            NumSampleAverages=cfg.NumSampleAverages,
            TempCalcMethod=cfg.TempCalc,
            ThermistorBeta=cfg.ThermistorBeta,
            AsyncCaptureDeltaMicroVolts=cfg.AsyncCaptureDeltaMicroVolts,
            SensorOrder=cfg.SensorOrder,
            ),
        ]
    )

    db.add_data_channels(
        [ DataChannelGt(
            Name=f"{reader}-depth{i}-device",
            DisplayName=f"{reader.capitalize()} Depth {i} Device Temp",
            AboutNodeName=f"{reader}-depth{i}",
            CapturedByNodeName=reader,
            TelemetryName=TelemetryName.WaterTempCTimes1000,
            TerminalAssetAlias=db.terminal_asset_alias,
            Id=db.make_channel_id(f"{reader}-depth{i}-device")
            ) for i in range(1,4)
        ]
    )

    if cfg.SendMicroVolts:
        db.add_data_channels(
            [ DataChannelGt(
                Name=f"{reader}-depth{i}-micro-v",
                DisplayName=f"{reader.capitalize()} Depth {i} MicroVolts",
                AboutNodeName=f"{reader}-depth{i}",
                CapturedByNodeName=reader,
                TelemetryName=TelemetryName.MicroVolts,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id=db.make_channel_id(f"{reader}-depth{i}-micro-v")
                ) for i in range(1,4)
            ]
        )
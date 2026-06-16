from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import (
    ActorClass,
    Gw1DeviceType,
    GwQuantity,
    TelemetryName,
    Unit,
)
from gwsproto.named_types import (
    ChannelConfig,
    DataChannelGt,
    SimPicoTankModuleComponentGt,
    SpaceheatNodeGt,
)

from layout_gen import LayoutDb
from layout_gen.tank3 import Tank3Cfg

# A simulated tank module reports the same channels as a real PicoTankModule3
# (see tank3.py), but its DeviceType marks it as a GridWorks sim sensor so the
# scada drives it through the simulated-test-environment path rather than a real
# pico. DeviceType value pending Jessica's review (see fixture_layouts wiring).
SIM_TANK_DEVICE_TYPE = Gw1DeviceType.GridworksSimSensor


def add_simulated_tanks(db: LayoutDb) -> None:
    """Add the buffer simulated tank. Storage tanks are added by the caller via
    add_sim_tank for tank1..tankN (TotalStoreTanks)."""
    add_sim_tank(db, "buffer")


def add_sim_tank(db: LayoutDb, reader: str) -> None:

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
        ]
        + [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(f"{reader}-depth{i}"),
                Name=f"{reader}-depth{i}",
                ActorClass=ActorClass.NoActor,
                DisplayName=f"{reader}-depth{i}",
            )
            for i in range(1, 4)
        ]
    )

    config_list = []
    for i in range(1, 4):
        config_list.append(
            ChannelConfig(
                ChannelName=f"{reader}-depth{i}-device",
                CapturePeriodS=cfg.CapturePeriodS,
                AsyncCapture=True,
                AsyncCaptureDelta=cfg.AsyncCaptureDeltaMicroVolts,
                Exponent=3,
                Unit=Unit.Celcius,
            )
        )
        if cfg.SendMicroVolts:
            config_list.append(
                ChannelConfig(
                    ChannelName=f"{reader}-depth{i}-micro-v",
                    CapturePeriodS=cfg.CapturePeriodS,
                    AsyncCapture=True,
                    AsyncCaptureDelta=cfg.AsyncCaptureDeltaMicroVolts,
                    Exponent=6,
                    Unit=Unit.VoltsRms,
                )
            )

    db.add_components(
        [
            SimPicoTankModuleComponentGt(
                ComponentId=component_id,
                DeviceType=SIM_TANK_DEVICE_TYPE,
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
        [
            DataChannelGt(
                Name=f"{reader}-depth{i}-device",
                DisplayName=f"{reader.capitalize()} Depth {i} Device Temp",
                AboutNodeName=f"{reader}-depth{i}",
                CapturedByNodeName=reader,
                TelemetryName=TelemetryName.WaterTempCTimes1000,
                Quantity=GwQuantity.Temperature,
                TerminalAssetAlias=db.terminal_asset_alias,
                Id=db.make_channel_id(f"{reader}-depth{i}-device"),
            )
            for i in range(1, 4)
        ]
    )

    if cfg.SendMicroVolts:
        db.add_data_channels(
            [
                DataChannelGt(
                    Name=f"{reader}-depth{i}-micro-v",
                    DisplayName=f"{reader.capitalize()} Depth {i} MicroVolts",
                    AboutNodeName=f"{reader}-depth{i}",
                    CapturedByNodeName=reader,
                    TelemetryName=TelemetryName.MicroVolts,
                    Quantity=GwQuantity.Voltage,
                    TerminalAssetAlias=db.terminal_asset_alias,
                    Id=db.make_channel_id(f"{reader}-depth{i}-micro-v"),
                )
                for i in range(1, 4)
            ]
        )

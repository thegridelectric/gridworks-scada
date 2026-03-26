# subsystems/zones/nolan.py

from layout_gen.core import LayoutDb

from gwsproto.enums import ActorClass, GwUnit, GwQuantity, EmissionMethod, TelemetryName
from gwsproto.named_types import (
    SpaceheatNodeGt,
    DataChannelGt,
    DerivedChannelGt,
)

from gwsproto.names.hydronic_spaceheat import (
    HydronicSpaceheatZoneNodeNames,
    HydronicSpaceheatZoneChannelNames,
)

from layout_gen.subsystems.zones.config import ZoneConfig


class NolanZoneImplementation:

    def add_zone(
        self,
        db: LayoutDb,
        *,
        nodes: HydronicSpaceheatZoneNodeNames,
        channels: HydronicSpaceheatZoneChannelNames,
        cfg: ZoneConfig,
    ) -> None:

        # -----------------------------
        # 1. Zone node (semantic)
        # -----------------------------
        db.add_nodes([
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(nodes.zone),
                Name=nodes.zone,
                ActorClass=ActorClass.NoActor,
                DisplayName=f"Zone {cfg.name}",
            ),
        ])

        # -----------------------------
        # 2. Whitewire opto node
        # -----------------------------
        opto_node = f"{nodes.whitewire}-opto"

        db.add_nodes([
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(opto_node),
                Name=opto_node,
                ActorClass=ActorClass.GpioSensor,
                DisplayName=f"{cfg.name} whitewire opto",
            ),
        ])

        # -----------------------------
        # 3. Opto input channel
        # -----------------------------
        opto_channel = f"{channels.base}-opto-input"

        db.add_data_channels([
            DataChannelGt(
                Id=db.make_channel_id(opto_channel),
                Name=opto_channel,
                AboutNodeName=nodes.whitewire,
                CapturedByNodeName=opto_node,
                TerminalAssetAlias=db.terminal_asset_alias,
                DisplayName=f"{cfg.name} whitewire input",
                TelemetryName=TelemetryName.BinaryState,
            )
        ])

        # -----------------------------
        # 4. Heat call (derived)
        # -----------------------------
        db.add_derived_channels([
            DerivedChannelGt(
                Id=db.make_derived_channel_id(channels.heat_call),
                Name=channels.heat_call,
                CreatedByNodeName="derived-generator",
                InputChannelNames=[opto_channel],
                OutputUnit=GwUnit.Unitless,
                OutputQuantity=GwQuantity.Unitless,
                TerminalAssetAlias=db.terminal_asset_alias,
                Strategy="heat-call",
                EmissionMethod=EmissionMethod.AsyncAndPeriodic,
                AsyncEmitDelta=1,
                EmitPeriodS=300,
                Parameters={
                    "Interpretation": "DigitalZeroIsActive"
                },
                DisplayName=f"{cfg.name} heat call",
            )
        ])
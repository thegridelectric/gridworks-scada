from gwsproto.enums import ActorClass, EmissionMethod, GwQuantity, GwUnit
from gwsproto.named_types import (DerivedChannelGt, RequiredEnergyLayered,
                                  SpaceheatNodeGt, UsableEnergyLayered)
from gwsproto.names.core.node_names import CoreNodeNames as CNN
from gwsproto.names.hydronic_spaceheat.channel_names import \
    HydronicSpaceheatChannelNames as HCN
from gwsproto.names.hydronic_spaceheat.node_names import \
    HydronicSpaceheatNodeNames as HNN
from layout_gen.core import LayoutDb


def add_hydronic_system_topology(
        db: LayoutDb,
        use_sieg_loop: bool,
    ) -> None:

    try:
        _ = db.terminal_asset_alias
    except Exception as e:
        raise Exception("Call apply_site_config before add_hydronic_system_topology") from e
    _add_core_nodes(db)
    if use_sieg_loop:
        _add_sieg_loop(db)
    add_required_and_usable_energy_channels(db)


def _add_core_nodes(db: LayoutDb) -> None:
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.primary_scada),
                Name=CNN.primary_scada,
                ActorClass=ActorClass.PrimaryScada,
                DisplayName="Primary Scada",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.secondary_scada),
                Name=CNN.secondary_scada,
                ActorClass=ActorClass.SecondaryScada,
                DisplayName="Secondary Scada"
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.admin),
                Name=CNN.admin,
                Handle=CNN.admin,
                ActorClass=ActorClass.NoActor,
                DisplayName="Local Admin",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.auto),
                Name=CNN.auto,
                Handle=CNN.auto,
                ActorClass=ActorClass.NoActor,
                DisplayName="Auto - FSM for dispatch contract",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.ltn),
                Name=CNN.ltn,
                ActorClass=ActorClass.NoActor,
                DisplayName="LeafTransactiveNode",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.leaf_ally),
                Name=CNN.leaf_ally,
                ActorHierarchyName=f"{CNN.primary_scada}.{CNN.leaf_ally}",
                Handle=f"{CNN.ltn}.{CNN.leaf_ally}",
                ActorClass=ActorClass.LeafAlly,
                DisplayName="Leaf Ally",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(HNN.pico_cycler),
                Name=HNN.pico_cycler,
                ActorHierarchyName=f"{CNN.primary_scada}.{HNN.pico_cycler}",
                Handle=f"{CNN.auto}.{HNN.pico_cycler}",
                ActorClass=ActorClass.PicoCycler,
                DisplayName="Pico Cycler - responsible for power cycling the 5VDC bus",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.derived_generator),
                Name=CNN.derived_generator,
                ActorHierarchyName=f"{CNN.primary_scada}.{CNN.derived_generator}",
                ActorClass=ActorClass.DerivedGenerator,
                DisplayName="Derived Generator",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(CNN.local_control),
                Name=CNN.local_control,
                ActorHierarchyName=f"{CNN.primary_scada}.{CNN.local_control}",
                Handle=f"{CNN.auto}.{CNN.local_control}",
                ActorClass=ActorClass.LocalControl,
                DisplayName="LocalControl",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(HNN.local_control_normal),
                Name=HNN.local_control_normal,
                Handle=f"{CNN.auto}.{CNN.local_control}.{HNN.local_control_normal}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Normal",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(HNN.local_control_backup),
                Name=HNN.local_control_backup,
                Handle=f"{CNN.auto}.{CNN.local_control}.{HNN.local_control_backup}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Backup",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(HNN.local_control_scada_blind),
                Name=HNN.local_control_scada_blind,
                Handle=f"{CNN.auto}.{CNN.local_control}.{HNN.local_control_scada_blind}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Scada Blind",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(HNN.hp_boss),
                Name=HNN.hp_boss,
                ActorHierarchyName=f"{CNN.primary_scada}.{HNN.hp_boss}",
                Handle=f"{CNN.auto}.{CNN.local_control}.{HNN.local_control_normal}.{HNN.hp_boss}",
                ActorClass=ActorClass.HpBoss,
                DisplayName="HeatpumpBoss",
            ),
            
        ]
    )

def _add_sieg_loop(db: LayoutDb) -> None:
    db.add_nodes(
        [
        SpaceheatNodeGt(
            ShNodeId=db.make_node_id(HNN.sieg_loop),
            Name=HNN.sieg_loop,
            ActorHierarchyName=f"{CNN.primary_scada}.{HNN.sieg_loop}",
            Handle=f"{CNN.auto}.{CNN.local_control}.{HNN.local_control_normal}.{HNN.sieg_loop}",
            ActorClass=ActorClass.SiegLoop,
            DisplayName="Siegenthaler Loop",
        ),
        ]
    )

    db.add_derived_channels(
        [DerivedChannelGt(
        Id=db.make_derived_channel_id(HCN.hp_keep_seconds_x_10),
        Name=HCN.hp_keep_seconds_x_10,
        CreatedByNodeName=HNN.sieg_loop,
        InputChannelNames=[],
        OutputUnit=GwUnit.SecondsX10,
        OutputQuantity=GwQuantity.Time,
        EmissionMethod=EmissionMethod.AsyncAndPeriodic,
        EmitPeriodS=300,
        AsyncEmitDelta=5,
        TerminalAssetAlias=db.terminal_asset_alias,
        Strategy="integrate-relay-motion",
        DisplayName="Seconds of keep Siegenthaler loop",
        )
    ]
    )
    

def add_required_and_usable_energy_channels(db: LayoutDb) -> None:
    channels = [
        DerivedChannelGt(
            Id=db.make_derived_channel_id(HCN.usable_energy),
            Name=HCN.usable_energy,
            CreatedByNodeName=CNN.derived_generator,
            InputChannelNames=[],
            OutputUnit=GwUnit.WattHours,
            OutputQuantity=GwQuantity.Energy,
            TerminalAssetAlias=db.terminal_asset_alias,
            Strategy="system-model",
            EmissionMethod=EmissionMethod.Periodic,
            EmitPeriodS=60,
            Parameters={
                "EnergyModel": UsableEnergyLayered().model_dump()
            },
            DisplayName="Usable Energy Wh",
            ),
        DerivedChannelGt(
            Id=db.make_derived_channel_id(HCN.required_energy),
            Name=HCN.required_energy,
            CreatedByNodeName=CNN.derived_generator,
            InputChannelNames=[],
            OutputUnit=GwUnit.WattHours,
            OutputQuantity=GwQuantity.Energy,
            TerminalAssetAlias=db.terminal_asset_alias,
            EmissionMethod=EmissionMethod.Periodic,
            EmitPeriodS=60,
            Strategy="system-model",
            Parameters={
                "EnergyModel": RequiredEnergyLayered().model_dump()
            },
            DisplayName="Required Energy Wh",
            ),
        ]

    db.add_derived_channels(channels)
    
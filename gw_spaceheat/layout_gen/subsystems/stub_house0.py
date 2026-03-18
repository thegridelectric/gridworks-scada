import uuid
from dataclasses import dataclass
from gwsproto.names.house0.node_names import House0NodeNames as H0NN
from gwsproto.names.house0.channel_names import House0ChannelNames as H0CN
from gwsproto.enums import (
    ActorClass,
    EmissionMethod,
    FlowManifoldVariant,
    GwQuantity,
    GwUnit,
)
from gwsproto.named_types import (
    DerivedChannelGt,
    SpaceheatNodeGt,
    RequiredEnergyLayered,
    UsableEnergyLayered
)

from layout_gen.core import LayoutDb

@dataclass
class House0StubConfig:
    flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0
    use_sieg_loop: bool = False
    ltn_gnode_alias: str = "ltn.orange"
    terminal_asset_alias: str | None = None
    scada_display_name: str = "Dummy Orange Scada"
    add_stub_power_meter: bool = True
    power_meter_cac_alias: str = "Dummy Power Meter Cac"
    power_meter_component_alias: str = "Dummy Power Meter Component"
    power_meter_node_display_name: str = "Dummy Power Meter"
    boost_element_display_name: str = "Dummy Boost Element"
    

def add_stub_scadas(
        db: LayoutDb,
        cfg: House0StubConfig | None = None,
    ):
    if cfg is None:
        cfg = House0StubConfig()
    if db.loaded.g_nodes:
        db.misc.update(db.loaded.g_nodes)
    else:
        db.misc["MyLeafTransactiveNodeGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": cfg.ltn_gnode_alias,
            "DisplayName": "LeafTransactiveNode",
            "GNodeStatus": "Active",
            "GNodeClass": "LeafTransactiveNode"
        }
        db.misc["MyScadaGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": f"{cfg.ltn_gnode_alias}.scada",
            "DisplayName": "Scada GNode",
            "GNodeStatus": "Active",
            "GNodeClass": "Scada"
        }
        ta_alias = f"{cfg.ltn_gnode_alias}.ta"
        if cfg.terminal_asset_alias:
            ta_alias = cfg.terminal_asset_alias
        db.misc["MyTerminalAssetGNode"] = {
            "GNodeId": str(uuid.uuid4()),
            "Alias": ta_alias,
            "DisplayName": "TerminalAsset GNode",
            "GNodeStatus": "Active",
            "GNodeClass": "TerminalAsset"
            }

    db.misc["Strategy"] = "House0"
    db.misc["FlowManifoldVariant"] = cfg.flow_manifold_variant
    db.misc["UseSiegLoop"] = cfg.use_sieg_loop
    db.add_nodes(
        [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.primary_scada),
                Name=H0NN.primary_scada,
                ActorClass=ActorClass.PrimaryScada,
                DisplayName=cfg.scada_display_name,
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.secondary_scada),
                Name=H0NN.secondary_scada,
                ActorClass=ActorClass.SecondaryScada,
                DisplayName="Secondary Scada"
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.admin),
                Name=H0NN.admin,
                Handle=H0NN.admin,
                ActorClass=ActorClass.NoActor,
                DisplayName="Local Admin",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.auto),
                Name=H0NN.auto,
                Handle=H0NN.auto,
                ActorClass=ActorClass.NoActor,
                DisplayName="Auto - FSM for dispatch contract",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.ltn),
                Name=H0NN.ltn,
                ActorClass=ActorClass.NoActor,
                DisplayName="LeafTransactiveNode",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.leaf_ally),
                Name=H0NN.leaf_ally,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.leaf_ally}",
                Handle=f"{H0NN.ltn}.{H0NN.leaf_ally}",
                ActorClass=ActorClass.LeafAlly,
                DisplayName="Leaf Ally",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.pico_cycler),
                Name=H0NN.pico_cycler,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.pico_cycler}",
                Handle=f"auto.{H0NN.pico_cycler}",
                ActorClass=ActorClass.PicoCycler,
                DisplayName="Pico Cycler - responsible for power cycling the 5VDC bus",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.derived_generator),
                Name=H0NN.derived_generator,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.derived_generator}",
                ActorClass=ActorClass.DerivedGenerator,
                DisplayName="Derived Generator",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.local_control),
                Name=H0NN.local_control,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.local_control}",
                Handle=f"auto.{H0NN.local_control}",
                ActorClass=ActorClass.LocalControl,
                DisplayName="LocalControl",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.local_control_normal),
                Name=H0NN.local_control_normal,
                Handle=f"auto.{H0NN.local_control}.{H0NN.local_control_normal}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Normal",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.local_control_backup),
                Name=H0NN.local_control_backup,
                Handle=f"auto.{H0NN.local_control}.{H0NN.local_control_backup}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Backup",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.local_control_scada_blind),
                Name=H0NN.local_control_scada_blind,
                Handle=f"auto.{H0NN.local_control}.{H0NN.local_control_scada_blind}",
                ActorClass=ActorClass.NoActor,
                DisplayName="LocalControl Scada Blind",
            ),
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.hp_boss),
                Name=H0NN.hp_boss,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.hp_boss}",
                Handle=f"auto.{H0NN.local_control}.{H0NN.local_control_normal}.{H0NN.hp_boss}",
                ActorClass=ActorClass.HpBoss,
                DisplayName="HeatpumpBoss",
            ),
            
        ]
    )

    if cfg.use_sieg_loop:
        db.add_nodes(
            [
            SpaceheatNodeGt(
                ShNodeId=db.make_node_id(H0NN.sieg_loop),
                Name=H0NN.sieg_loop,
                ActorHierarchyName=f"{H0NN.primary_scada}.{H0NN.sieg_loop}",
                Handle=f"{H0NN.auto}.{H0NN.local_control}.{H0NN.local_control_normal}.{H0NN.sieg_loop}",
                ActorClass=ActorClass.SiegLoop,
                DisplayName="Siegenthaler Loop",
            ),
            ]
        )
        EmissionMethod.AsyncAndPeriodic
        db.add_derived_channels(
            [DerivedChannelGt(
            Id = db.make_derived_channel_id(H0CN.hp_keep_seconds_x_10),
            Name = H0CN.hp_keep_seconds_x_10,
            CreatedByNodeName = H0NN.sieg_loop,
            InputChannelNames=[],
            OutputUnit=GwUnit.SecondsX10,
            OutputQuantity=GwQuantity.Time,
            EmissionMethod=EmissionMethod.AsyncAndPeriodic,
            EmitPeriodS=300,
            AsyncEmitDelta=5,
            TerminalAssetAlias = db.terminal_asset_alias,
            Strategy = "integrate-relay-motion",
            DisplayName = "Seconds of keep Siegenthaler loop",
            )
        ]
        )

    add_house0_derived_channels(db)

def add_house0_derived_channels(db: LayoutDb) -> None:
    channels = [
        DerivedChannelGt(
            Id = db.make_derived_channel_id(H0CN.usable_energy),
            Name = H0CN.usable_energy,
            CreatedByNodeName=H0NN.derived_generator,
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
            Id = db.make_derived_channel_id(H0CN.required_energy),
            Name = H0CN.required_energy,
            CreatedByNodeName = H0NN.derived_generator,
            InputChannelNames=[],
            OutputUnit=GwUnit.WattHours,
            OutputQuantity=GwQuantity.Energy,
            TerminalAssetAlias = db.terminal_asset_alias,
            EmissionMethod=EmissionMethod.Periodic,
            EmitPeriodS=60,
            Strategy = "system-model",
            Parameters={
                "EnergyModel": RequiredEnergyLayered().model_dump()
            },
            DisplayName = "Required Energy Wh",
            ),
        ]

    db.add_derived_channels(channels)
    
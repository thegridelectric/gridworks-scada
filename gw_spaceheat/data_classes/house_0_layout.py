import json
from pathlib import Path
from typing import Any, List, Literal, Optional

from gw.errors import DcError
from gwproto.enums import ActorClass
from gwproto.data_classes.components import Component
from gwproto.data_classes.data_channel import DataChannel
from gwproto.data_classes.hardware_layout import (
    HardwareLayout,
    LoadArgs,
    LoadError,
)

from data_classes.house_0_names import H0CN, H0N
from enums import FlowManifoldVariant, HomeAloneStrategy

from gwproto.data_classes.sh_node import ShNode
from gwproto.data_classes.synth_channel import SynthChannel
from gwproto.default_decoders import (
    CacDecoder,
    ComponentDecoder,
)
from gwproto.named_types import ComponentAttributeClassGt

class House0LoadArgs(LoadArgs):
    flow_manifold_variant: FlowManifoldVariant
    use_sieg_loop: bool
class House0Layout(HardwareLayout):
    zone_list: List[str]
    total_store_tanks: int


    def __init__(  # noqa: PLR0913
        self,
        layout: dict[Any, Any],
        *,
        cacs: dict[str, ComponentAttributeClassGt],  # by id
        components: dict[str, Component],  # by id
        nodes: dict[str, ShNode],  # by name
        data_channels: dict[str, DataChannel],  # by name
        synth_channels: dict[str, SynthChannel],
        flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0,
        use_sieg_loop: bool = False,
    ) -> None:
        super().__init__(
            layout=layout,
            cacs=cacs,
            components=components,
            nodes=nodes,
            data_channels=data_channels,
            synth_channels=synth_channels,
        )
        self.flow_manifold_variant = flow_manifold_variant
        self.use_sieg_loop = use_sieg_loop

        # Bolted on right now
        required_keys = ["ZoneList", "TotalStoreTanks"]
        for key in required_keys:
            if key not in layout:
                raise DcError(f"House0 requires {key}!")


        self.zone_list = layout["ZoneList"]
        self.total_store_tanks = layout["TotalStoreTanks"]

        self.channel_names = H0CN(self.total_store_tanks, self.zone_list)
        if not isinstance(self.total_store_tanks, int):
            raise TypeError("TotalStoreTanks must be an integer")
        if not 1 <= self.total_store_tanks <= 6:
            raise ValueError("Must have between 1 and 6 store tanks")
        if not isinstance(self.zone_list, List):
            raise TypeError("ZoneList must be a list")
        if not 1 <= len(self.zone_list) <= 6:
            raise ValueError("Must have between 1 and 6 store zones")
        self.h0n = H0N(self.total_store_tanks, self.zone_list)

    @classmethod
    def validate_house0(  # noqa: C901
        cls,
        load_args: House0LoadArgs,
        *,
        raise_errors: bool,
        errors: Optional[list[LoadError]] = None,
    ) -> None:
        nodes = load_args["nodes"]
        data_channels = load_args["data_channels"]
        errors_caught = []
        flow_manifold_variant = load_args["flow_manifold_variant"]
        use_sieg_loop = load_args["use_sieg_loop"]

        # Can't use the siegenthaler loop in the code if it isn't in the plumbing
        if use_sieg_loop and flow_manifold_variant != FlowManifoldVariant.House0Sieg:
            raise DcError("Cannot use Sieg Loop when FlowManifoldVariant is not House0Sieg!")

        # Make sure sieg relays, sieg flow and sieg temp nodes and channels exist
        if flow_manifold_variant == FlowManifoldVariant.House0Sieg:
            try:
                cls.check_house0_sieg_manifold(data_channels)
            except Exception as e:
                if raise_errors:
                    raise
                errors_caught.append(LoadError("hardware.layout", nodes, e))


        if use_sieg_loop: # HpBoss and SiegLoop need to be actors
            try:
                cls.check_actors_when_using_sieg_loop(nodes)
            except Exception as e:
                if raise_errors:
                    raise
                errors_caught.append(LoadError("hardware.layout", nodes, e))
        else: # HpBoss and SiegLoop should NOT be actors
            try:
                cls.check_actors_when_not_using_sieg_loop(nodes)
            except Exception as e:
                if raise_errors:
                    raise
                errors_caught.append(LoadError("hardware.layout", nodes, e))
    @classmethod
    def check_house0_sieg_manifold(cls, channels: dict[str, DataChannel]) -> None:
        # if H0CN.sieg_cold not in channels.keys():
        #     raise DcError(f"Need {H0CN.sieg_cold} channel with House0Sieg flow manifold variant")
        # if H0CN.sieg_flow not in channels.keys():
        #     raise DcError(f"Need {H0CN.sieg_flow} channel with House0Sieg flow manifold variant")
        if H0CN.hp_loop_on_off_relay_state not in channels.keys():
            raise DcError(f"Need {H0CN.hp_loop_on_off_relay_state} channel with House0Sieg flow manifold variant")
        if H0CN.hp_loop_keep_send_relay_state not in channels.keys():
            raise DcError(f"Need {H0CN.hp_loop_keep_send_relay_state} channel with House0Sieg flow manifold variant")

    @classmethod
    def check_actors_when_using_sieg_loop(cls, nodes: dict[str, ShNode]) -> None:
        if H0N.sieg_loop not in nodes.keys():
            raise DcError(f"Need a SiegLoop actor when using sieg loop!")
        sieg_loop = nodes[H0N.sieg_loop]
        if sieg_loop.actor_class != ActorClass.SiegLoop:
            raise DcError(f"SiegLoop actor {sieg_loop.name} shoud have actor class SiegLoop, not {sieg_loop.actor_class}")
        if H0N.hp_boss not in nodes.keys():
            raise DcError(f"Need HpBoss actor when using sieg loop!")
        hp_boss = nodes[H0N.hp_boss]
        if hp_boss.actor_class != ActorClass.HpBoss:
            raise DcError(f"HpBoss actor {hp_boss.name} shoud have actor class HpBoss, not {hp_boss.actor_class}")

    @classmethod
    def check_actors_when_not_using_sieg_loop(cls, nodes: dict[str, ShNode]) -> None:
        if H0N.sieg_loop in nodes.keys():
            raise DcError(f"If not using sieg loop, should not have node {H0N.sieg_loop}!")

    @property
    def ha_strategy(self) -> str:
        """Returns the current home alone strategy"""
        # Could be stored as a property or derived from a node
        ha_node = self.nodes.get(H0N.home_alone)
        return HomeAloneStrategy(HomeAloneStrategy(getattr(ha_node, "Strategy", None)))
    
    @property
    def actuators(self) -> List[ShNode]:
        return self.relays + self.zero_tens
    
    @property
    def relays(self) -> List[ShNode]:
        return [
            node for node in self.nodes.values()
            if node.ActorClass == ActorClass.Relay
        ]
    
    @property
    def zero_tens(self) -> List[ShNode]:
        return [
            node for node in self.nodes.values()
            if node.ActorClass == ActorClass.ZeroTenOutputer
        ]


    # overwrites base class to return correct object
    @classmethod
    def load(  # noqa: PLR0913
        cls,
        layout_path: Path | str,
        *,
        included_node_names: Optional[set[str]] = None,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        cac_decoder: Optional[CacDecoder] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> "House0Layout":
        with Path(layout_path).open() as f:
            layout = json.loads(f.read())
        return cls.load_dict(
            layout,
            included_node_names=included_node_names,
            raise_errors=raise_errors,
            errors=errors,
            cac_decoder=cac_decoder,
            component_decoder=component_decoder,
        )

    # overwrites base class to return correct object
    @classmethod
    def load_dict(  # noqa: PLR0913
        cls,
        layout: dict[Any, Any],
        *,
        included_node_names: Optional[set[str]] = None,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        cac_decoder: Optional[CacDecoder] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> "House0Layout":
        if errors is None:
            errors = []
        cacs = cls.load_cacs(
            layout=layout,
            raise_errors=raise_errors,
            errors=errors,
            cac_decoder=cac_decoder,
        )
        components = cls.load_components(
            layout=layout,
            cacs=cacs,
            raise_errors=raise_errors,
            errors=errors,
            component_decoder=component_decoder,
        )
        nodes = cls.load_nodes(
            layout=layout,
            components=components,
            raise_errors=raise_errors,
            errors=errors,
            included_node_names=included_node_names,
        )
        data_channels = cls.load_data_channels(
            layout=layout,
            nodes=nodes,
            raise_errors=raise_errors,
            errors=errors,
        )
        synth_channels = cls.load_synth_channels(
            layout=layout,
            nodes=nodes,
            raise_errors=raise_errors,
            errors=errors,
        )
        load_args: House0LoadArgs = {
            "cacs": cacs,
            "components": components,
            "nodes": nodes,
            "data_channels": data_channels,
            "synth_channels": synth_channels,
            "flow_manifold_variant": FlowManifoldVariant(layout.get("FlowManifoldVariant", "House0")),
            "use_sieg_loop": bool(layout.get("UseSiegLoop", False))
        }
        cls.resolve_links(
            load_args["nodes"],
            load_args["components"],
            raise_errors=raise_errors,
            errors=errors,
        )
        cls.validate_layout(load_args, raise_errors=raise_errors, errors=errors)
        cls.validate_house0(load_args, raise_errors=raise_errors, errors=errors)
        return House0Layout(layout, **load_args)

    @property
    def home_alone(self) -> ShNode:
        return self.node(H0N.home_alone)
    
    @property
    def auto_node(self) -> ShNode:
        return self.node(H0N.auto)
    
    @property
    def atomic_ally(self) -> ShNode:
        return self.node(H0N.atomic_ally)
    
    @property
    def atn(self) -> ShNode:
        return self.node(H0N.atn)
    
    @property
    def pico_cycler(self) -> ShNode:
        return self.node(H0N.pico_cycler)

    @property
    def vdc_relay(self) -> ShNode:
        return self.node(H0N.vdc_relay)

    @property
    def tstat_common_relay(self) -> ShNode:
        return self.node(H0N.tstat_common_relay)

    @property
    def charge_discharge_relay(self) -> ShNode:
        return self.node(H0N.store_charge_discharge_relay)#

    def scada2_gnode_name(self) -> str:
        return f"{self.scada_g_node_alias}.{H0N.secondary_scada}"

def deserialize_house0_load_args(data: dict) -> House0LoadArgs:
    valid_keys = set(House0LoadArgs.__annotations__.keys())

    # Validate the FlowManifoldVariant
    data["FlowManifoldVariant"] = FlowManifoldVariant(data.get("FlowManifoldVariant", "House0"))
    # Validate use_sieg_loop
    data["UseSiegLoop"] = bool(data.get("UseSiegLoop", False))
    # TypedDict expects a regular dictionary, so we just pass it in
    return House0LoadArgs(**data)


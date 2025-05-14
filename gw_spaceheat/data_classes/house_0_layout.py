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


class House0Layout(HardwareLayout):
    zone_list: List[str]
    total_store_tanks: int


    def __init__(  # noqa: PLR0913
        self,
        layout: dict[Any, Any],
        cacs: Optional[dict[str, ComponentAttributeClassGt]] = None,  # by id
        components: Optional[dict[str, Component]] = None,  # by id
        nodes: Optional[dict[str, ShNode]] = None,  # by name
        data_channels: Optional[dict[str, DataChannel]] = None,  # by name
        synth_channels: Optional[dict[str, SynthChannel]] = None,
    ) -> None:
        super().__init__(
            layout=layout,
            cacs=cacs,
            components=components,
            nodes=nodes,
            data_channels=data_channels,
            synth_channels=synth_channels,
        )
        if "ZoneList" not in layout:
            raise DcError(
                "House0 requires ZoneList, a list of the thermostat zone names!"
            )
        if "TotalStoreTanks" not in layout:
            raise DcError("House0 requires TotalStoreTanks")
        if "FlowManifoldVariant" not in layout:
            raise DcError("House0 requires FlowManifoldVariant")
        if not self.layout["FlowManifoldVariant"] in FlowManifoldVariant.values():
            raise DcError(f"FlowManifoldVariant must belong to {FlowManifoldVariant.values()}!")
        self.flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant(self.layout["FlowManifoldVariant"])
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
        
        #TODO: verify that if FlowManifoldVariant is House0Sieg, that
        # the layout has the siegenthaler relays and the sieg-flow
        # flow meter

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
        load_args: LoadArgs = {
            "cacs": cacs,
            "components": components,
            "nodes": nodes,
            "data_channels": data_channels,
            "synth_channels": synth_channels,
        }
        cls.resolve_links(
            load_args["nodes"],
            load_args["components"],
            raise_errors=raise_errors,
            errors=errors,
        )
        cls.validate_layout(load_args, raise_errors=raise_errors, errors=errors)
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
        return self.node(H0N.store_charge_discharge_relay)

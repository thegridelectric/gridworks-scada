"""
LayoutDb builds hardware layout dictionaries; LayoutIDMap loads existing ones.

Flow:
    LayoutIDMap → LayoutDb → dict → HardwareLayout

LayoutIDMap: load + index existing layout (IDs, aliases)
LayoutDb: construct layout, reuse IDs, enforce uniqueness
HardwareLayout: 
  - runtime interpretation (zones, tanks, actors)
  - provides validation

Invariant: stable IDs across regeneration.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Optional, Sequence

from gwsproto.enums import MakeModel
from gwsproto.errors import DcError
from gwsproto.named_types import (ComponentAttributeClassGt, ComponentGt,
                                  DataChannelGt, DerivedChannelGt,
                                  SpaceheatNodeGt)
from gwsproto.type_helpers import CACS_BY_MAKE_MODEL
from layout_gen.core.layout_id_map import LayoutIDMap


LayoutEntry = (
    ComponentAttributeClassGt
    | ComponentGt
    | SpaceheatNodeGt
    | DataChannelGt
    | DerivedChannelGt
)

class LayoutDb:
    """Builder for hardware layout dictionaries consumed by HardwareLayout."""

    lists: dict[str, list[LayoutEntry]]
    misc: dict[str, Any]
    cacs_by_id: dict[str, ComponentAttributeClassGt]
    components_by_id: dict[str, ComponentGt]
    component_lists: dict[str, list[ComponentGt]]

    nodes_by_id: dict[str, SpaceheatNodeGt]
    channels_by_id: dict[str, DataChannelGt]
    derived_channels_by_id: dict[str, DerivedChannelGt]

    loaded: LayoutIDMap
    maps: LayoutIDMap

    def __init__(
        self,
        existing_layout: LayoutIDMap | None = None,
    ):
        self.lists = {}
        self.misc =  {}
        self.misc.update(self.loaded.g_nodes)
        self.lists["OtherComponents"] = []

        self.cacs_by_id = {}
        self.components_by_id = {}
        self.component_lists = {}

        self.nodes_by_id = {}
        self.channels_by_id = {}
        self.derived_channels_by_id = {}

        self.loaded = existing_layout or LayoutIDMap()
        self.maps = LayoutIDMap()

        # hydrate maps with loaded state
        self.maps.cacs_by_alias = dict(self.loaded.cacs_by_alias)
        self.maps.components_by_alias = dict(self.loaded.components_by_alias)
        self.maps.nodes_by_name = dict(self.loaded.nodes_by_name)
        self.maps.channels_by_name = dict(self.loaded.channels_by_name)
        self.maps.derived_channels_by_name = dict(self.loaded.derived_channels_by_name)

    @property
    def terminal_asset_alias(self) -> str:
        ta = self.misc.get("MyTerminalAssetGNode")
        if not ta:
            raise Exception("Missing MyTerminalAssetGNode in layout")
        return ta["Alias"]

    def cac_id_by_alias(self, alias: str) -> Optional[str]:
        return self.maps.cacs_by_alias.get(alias, None)

    def component_id_by_alias(self, component_alias: str) -> Optional[str]:
        return self.maps.components_by_alias.get(component_alias, None)

    def node_id_by_name(self, node_name: str) -> Optional[str]:
        return self.maps.nodes_by_name.get(node_name, None)
    
    def channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.channels_by_name.get(name, None)
    
    def derived_channel_id_by_name(self, name: str) -> Optional[str]:
        return self.maps.derived_channels_by_name.get(name, None)

    def make_cac_id(
            self,
            *,
            make_model: MakeModel,
            cac_alias: str | None = None,
        ) -> str:
        if make_model == MakeModel.UNKNOWNMAKE__UNKNOWNMODEL:
            if cac_alias is None:
                raise Exception("For unknown MakeModel, MUST include cac_alias")
            return self.loaded.cacs_by_alias.get(cac_alias, str(uuid.uuid4()))
        elif make_model in CACS_BY_MAKE_MODEL:
                return CACS_BY_MAKE_MODEL[make_model]
        raise Exception(f"Unknown MakeModel {make_model}")

    def make_component_id(self, component_alias: str) -> str:
        return self.loaded.components_by_alias.get(component_alias, str(uuid.uuid4()))

    def make_node_id(self, node_name: str) -> str:
        return self.loaded.nodes_by_name.get(node_name, str(uuid.uuid4()))
    
    def make_channel_id(self, name: str) -> str:
        return self.loaded.channels_by_name.get(name, str(uuid.uuid4()))
    
    def make_derived_channel_id(self, name: str) -> str:
        return self.loaded.derived_channels_by_name.get(name, str(uuid.uuid4()))

    def add_cacs(self, cacs:Sequence[ComponentAttributeClassGt], layout_list_name: str = "OtherCacs"):
        for cac in cacs:
            if cac.ComponentAttributeClassId in self.cacs_by_id:
                raise ValueError(
                    f"ERROR: cac with id <{cac.ComponentAttributeClassId}> "
                    "already present"
                )
            self.cacs_by_id[cac.ComponentAttributeClassId] = cac
            if cac.DisplayName is None:
                display_name = ""
            else:
                display_name = cac.DisplayName
            self.maps.add_cacs_by_alias(
                    cac.ComponentAttributeClassId,
                    cac.MakeModel,
                    display_name,
                )

            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(cac)

    def add_components(self, components: Sequence[ComponentGt], layout_list_name: str = "OtherComponents"):
        for component in components:
            if not component.DisplayName:
                raise DcError(f"component {component.ComponentId} missing display name! need that for layout gen ...")
            if component.ComponentId in self.components_by_id:
                raise ValueError(
                    f"ERROR. Component with id {component.ComponentId} "
                    "already present."
                )
            if component.DisplayName in self.maps.components_by_alias:
                raise ValueError(
                    f"ERROR. Component with DisplayName {component.DisplayName} "
                    "already present."
                )
            self.components_by_id[component.ComponentId] = component
            self.maps.add_component(
                component.ComponentId,
                component.DisplayName,
            )
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(component)

    def add_nodes(self, nodes: Sequence[SpaceheatNodeGt]):
        for node in nodes:
            if node.ShNodeId in self.nodes_by_id:
                raise ValueError(
                    f"ERROR Node id {node.ShNodeId} already present."
                )
            if node.Name in self.maps.nodes_by_name:
                raise ValueError(
                    f"ERROR Node name {node.Name} already present."
                )
            self.nodes_by_id[node.ShNodeId] = node
            self.maps.add_node(node.ShNodeId, node.Name)
            layout_list_name = "ShNodes"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(node)
    
    def add_data_channels(self, dcs: Sequence[DataChannelGt]):
        for dc in dcs:
            if dc.Id in self.channels_by_id:
                raise ValueError(
                    f"ERROR channel id {dc.Id} already present."
                )
            if dc.Name in self.maps.channels_by_name:
                raise ValueError(
                    f"ERROR Channel name {dc.Name} already present"
                )
            self.channels_by_id[dc.Id] = dc
            self.maps.add_channel(dc.Id, dc.Name)
            layout_list_name = "DataChannels"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(dc)

    def add_derived_channels(self, dcs: Sequence[DerivedChannelGt]):
        for dc in dcs:
            if dc.Id in self.derived_channels_by_id:
                raise ValueError(
                    f"ERROR derived channel id {dc.Id} already present."
                )
            if dc.Name in self.maps.derived_channels_by_name:
                raise ValueError(
                    f"ERROR Derived Channel name {dc.Name} already present"
                )
            self.derived_channels_by_id[dc.Id] = dc
            self.maps.add_derived_channel(dc.Id, dc.Name)
            layout_list_name = "DerivedChannels"
            if layout_list_name not in self.lists:
                self.lists[layout_list_name] = []
            self.lists[layout_list_name].append(dc)


    def dict(self) -> dict:
        d = dict(
            self.misc,
            **{
                list_name: [
                     entry.model_dump(by_alias=True, exclude_none=True) for entry in entries
                ]
                for list_name, entries in self.lists.items()
            }
        )
        return d

    def write(self, path: str | Path) -> None:
        with Path(path).open("w") as f:
            f.write(json.dumps(self.dict(), sort_keys=True, indent=2))
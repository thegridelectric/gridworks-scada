import copy
import json
import typing
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Optional, TypeVar

from gw.errors import DcError
from gwsproto.decoders import (
    CacDecoder,
    ComponentDecoder,
)
from gwsproto.default_decoders import (
    default_cac_decoder,
    default_component_decoder,
)

import gwsproto.data_classes.components
from gwsproto.data_classes.components import Ads111xBasedComponent, Component
from gwsproto.data_classes.components.component import ComponentOnly
from gwsproto.data_classes.components.electric_meter_component import (
    ElectricMeterComponent,
)
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.resolver import ComponentResolver
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.synth_channel import SynthChannel
from gwsproto.data_classes.telemetry_tuple import TelemetryTuple

from gwsproto.enums import ActorClass, TelemetryName
from gwsproto.named_types import (
    ComponentAttributeClassGt,
    ComponentGt,
    DataChannelGt,
    ElectricMeterCacGt,
    SpaceheatNodeGt,
)

T = TypeVar("T")


@dataclass
class LoadError:
    type_name: str
    src_dict: dict[Any, Any]
    exception: Exception


class LoadArgs(typing.TypedDict):
    cacs: dict[str, ComponentAttributeClassGt]
    components: dict[str, Component[Any, Any]]
    nodes: dict[str, ShNode]
    data_channels: dict[str, DataChannel]
    synth_channels: dict[str, SynthChannel]


class HardwareLayout:
    layout: dict[Any, Any]
    cacs: dict[str, ComponentAttributeClassGt]
    components: dict[str, Component[Any, Any]]
    components_by_type: dict[type[Any], list[Component[Any, Any]]]
    nodes: dict[str, ShNode]
    nodes_by_component: dict[str, str]
    data_channels: dict[str, DataChannel]
    synth_channels: dict[str, SynthChannel]

    GT_SUFFIX = "Gt"

    @classmethod
    def load_cacs(
        cls,
        layout: dict[str, Any],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        cac_decoder: Optional[CacDecoder] = None,
    ) -> dict[str, ComponentAttributeClassGt]:
        if errors is None:
            errors = []
        if cac_decoder is None:
            cac_decoder = default_cac_decoder
        cacs: dict[str, ComponentAttributeClassGt] = {}
        for type_name in [
            "Ads111xBasedCacs",
            "ResistiveHeaterCacs",
            "ElectricMeterCacs",
            "OtherCacs",
        ]:
            for cac_dict in layout.get(type_name, ()):
                try:
                    cac = cac_decoder.decode(cac_dict)
                    cacs[cac.ComponentAttributeClassId] = cac
                except Exception as e:  # noqa: PERF203
                    if raise_errors:
                        raise
                    errors.append(LoadError(type_name, cac_dict, e))
        return cacs

    @classmethod
    def get_data_class_name(cls, component_gt: ComponentGt) -> str:
        gt_class_name = component_gt.__class__.__name__
        if not gt_class_name.endswith(cls.GT_SUFFIX) or len(gt_class_name) <= len(
            cls.GT_SUFFIX
        ):
            raise DcError(  # noqa: TRY301
                f"Name of decoded component class ({gt_class_name}) "
                f"must end with <{cls.GT_SUFFIX}> "
                f"and be longer than {len(cls.GT_SUFFIX)} chars"
            )
        return gt_class_name[: -len(cls.GT_SUFFIX)]

    @classmethod
    def get_data_class_class(
        cls, component_gt: ComponentGt
    ) -> type[Component[Any, Any]]:
        return getattr(
            gwsproto.data_classes.components,
            cls.get_data_class_name(component_gt),
            ComponentOnly,
        )

    @classmethod
    def make_component(
        cls, component_gt: ComponentGt, cac: ComponentAttributeClassGt
    ) -> Component[Any, Any]:
        return cls.get_data_class_class(component_gt)(gt=component_gt, cac=cac)

    @classmethod
    def load_components(
        cls,
        layout: dict[Any, Any],
        cacs: dict[str, ComponentAttributeClassGt],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> dict[str, Component[Any, Any]]:
        if errors is None:
            errors = []
        if component_decoder is None:
            component_decoder = default_component_decoder
        components = {}
        for type_name in [
            "Ads111xBasedComponents",
            "ResistiveHeaterComponents",
            "ElectricMeterComponents",
            "OtherComponents",
        ]:
            for component_dict in layout.get(type_name, ()):
                try:
                    component_gt = component_decoder.decode(component_dict)
                    cac_gt = cacs.get(component_gt.ComponentAttributeClassId, None)
                    if cac_gt is None:
                        raise DcError(  # noqa: TRY301
                            f"cac {component_gt.ComponentAttributeClassId} not loaded for component "
                            f"<{component_gt.ComponentId}/<{component_gt.DisplayName}>\n"
                        )
                    components[component_gt.ComponentId] = cls.make_component(
                        component_gt,
                        cac_gt,
                    )
                except Exception as e:  # noqa: PERF203
                    if raise_errors:
                        raise
                    errors.append(LoadError(type_name, component_dict, e))
        return components

    @classmethod
    def make_node(
        cls,
        node_dict: dict[str, Any] | SpaceheatNodeGt,
        components: dict[str, Component[Any, Any]],
    ) -> ShNode:
        if isinstance(node_dict, SpaceheatNodeGt):
            node_gt = node_dict
        else:
            node_gt = SpaceheatNodeGt.model_validate(node_dict)
        if node_gt.ComponentId:
            component = components.get(node_gt.ComponentId)
            if component is None:
                raise ValueError(
                    f"ERROR. Component <{node_gt.ComponentId}> not loaded "
                    f"for node <{node_gt.Name}>"
                )
        else:
            component = None
        return ShNode(component=component, **node_gt.model_dump())

    @classmethod
    def load_nodes(
        cls,
        layout: dict[Any, Any],
        components: dict[str, Component[Any, Any]],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        included_node_names: Optional[set[str]] = None,
    ) -> dict[str, ShNode]:
        nodes = {}
        if errors is None:
            errors = []
        for node_dict in layout.get("ShNodes", []):
            try:
                node_name = node_dict["Name"]
                if included_node_names is None or node_name in included_node_names:
                    nodes[node_name] = cls.make_node(node_dict, components)
            except Exception as e:  # noqa: PERF203
                if raise_errors:
                    raise
                errors.append(LoadError("ShNode", node_dict, e))
        return nodes

    @classmethod
    def make_channel(
        cls, dc_dict: dict[str, Any], nodes: dict[str, ShNode]
    ) -> DataChannel:
        data_channel_gt = DataChannelGt.model_validate(dc_dict)
        about_node = nodes.get(data_channel_gt.AboutNodeName)
        captured_by_node = nodes.get(data_channel_gt.CapturedByNodeName)
        if about_node is None or captured_by_node is None:
            raise ValueError(
                f"ERROR. DataChannel related nodes must exist for {dc_dict.get('Name')}!\n"
                f"  For AboutNodeName <{data_channel_gt.AboutNodeName}> "
                f"got {about_node}\n"
                f"  for CapturedByNodeName <{data_channel_gt.CapturedByNodeName}>"
                f"got {captured_by_node}"
            )
        return DataChannel(
            about_node=about_node, captured_by_node=captured_by_node, **dc_dict
        )

    @classmethod
    def make_synth_channel(
        cls, synth_dict: dict[str, Any], nodes: dict[str, ShNode]
    ) -> SynthChannel:
        created_by_node_name = synth_dict.get("CreatedByNodeName", "")
        created_by_node = nodes.get(created_by_node_name)
        if created_by_node is None:
            raise ValueError(
                f"ERROR. SynthChannel related nodes must exist for {synth_dict.get('Name')}!\n"
                f"  For CreatedByNodeName<{created_by_node_name}> "
                f"got None!\n"
            )
        return SynthChannel(created_by_node=created_by_node, **synth_dict)

    @classmethod
    def check_dc_id_uniqueness(
        cls,
        data_channels: dict[str, DataChannel],
    ) -> None:
        id_counter = Counter(dc.Id for dc in data_channels.values())
        dupes = [node_id for node_id, count in id_counter.items() if count > 1]
        if dupes:
            raise DcError(f"Duplicate dc.Id(s) found: {dupes}")

    @classmethod
    def check_node_channel_consistency(
        cls, nodes: dict[str, ShNode], data_channels: dict[str, DataChannel]
    ) -> None:
        capturing_classes = [
            ActorClass.PowerMeter,
            ActorClass.MultipurposeSensor,
        ]
        active_nodes = [
            node for node in nodes.values() if node.ActorClass in capturing_classes
        ]
        for node in active_nodes:
            if node.component is None:
                my_channel_names = []
            else:
                my_channel_names = [
                    config.ChannelName for config in node.component.gt.ConfigList
                ]
            my_channels = [
                dc for dc in data_channels.values() if dc.Name in my_channel_names
            ]
            for channel in my_channels:
                if channel.CapturedByNodeName != node.Name:
                    raise DcError(
                        f"Channel {channel} should have CapturedByNodeName {node.Name}"
                    )

    @classmethod
    def check_data_channel_consistency(
        cls,
        nodes: dict[str, ShNode],
        components: dict[str, Component[Any, Any]],
        data_channels: dict[str, DataChannel],
    ) -> None:
        cls.check_dc_id_uniqueness(data_channels)
        dc_names_by_component: set[str] = set()
        for c in components.values():
            channel_names = {config.ChannelName for config in c.gt.ConfigList}
            if dc_names_by_component & channel_names:
                raise DcError(
                    f"Channel name overlap!: {dc_names_by_component & channel_names}"
                )
            dc_names_by_component.update(channel_names)
        actual_dc_names = {dc.Name for dc in data_channels.values()}
        if dc_names_by_component != actual_dc_names:
            by_comp = list(dc_names_by_component)
            by_comp.sort()
            actual = list(actual_dc_names)
            actual.sort()
            raise DcError(
                "Channel inconsistency! \n"
                f"From Components:{by_comp}\n"
                f"From DataChannel list:{actual}\n"
            )
        cls.check_node_channel_consistency(nodes, data_channels)

    @classmethod
    def check_actor_component_consistency(cls, nodes: dict[str, ShNode]) -> None:
        pm_nodes = [
            node for node in nodes.values() if node.ActorClass == ActorClass.PowerMeter
        ]
        for node in pm_nodes:
            if (
                node.component is None
                or node.component.gt.TypeName != "electric.meter.component.gt"
            ):
                raise DcError(
                    f"Power Meter node {node} needs ElectricMeterComponent."
                    f"Got component {node.component}"
                )
        em_nodes = [
            node
            for node in nodes.values()
            if node.ActorClass == ActorClass.MultipurposeSensor
        ]
        for node in em_nodes:
            multi_comp_type_names = ["ads111x.based.component.gt"]
            if (
                node.component is None
                or node.component.gt.TypeName not in multi_comp_type_names
            ):
                raise DcError(
                    f"Power Meter node {node} needs Component "
                    f"in {multi_comp_type_names}. Got component"
                    f"{node.component}"
                )

    @classmethod
    def check_handle_hierarchy(cls, nodes: dict[str, ShNode]) -> None:
        for n in nodes.values():
            boss_handle = cls.boss_handle(n.handle)
            # No dots in your name: you are your own boss
            if boss_handle:
                boss = next(
                    (n for n in nodes.values() if n.handle == boss_handle), None
                )
                if boss is None:
                    raise DcError(f"{n.name} is missing boss {boss_handle}")

    @classmethod
    def check_node_unique_ids(cls, nodes: dict[str, ShNode]) -> None:
        id_counter = Counter(node.ShNodeId for node in nodes.values())
        dupes = [node_id for node_id, count in id_counter.items() if count > 1]
        if dupes:
            raise DcError(f"Duplicate ShNodeId(s) found: {dupes}")

    @classmethod
    def check_transactive_metering_consistency(
        cls, nodes: dict[str, ShNode], data_channels: dict[str, DataChannel]
    ) -> None:
        transactive_nodes = {node for node in nodes.values() if node.InPowerMetering}
        transactive_channels = {
            dc for dc in data_channels.values() if dc.InPowerMetering
        }
        # Part 1: If a data channel is in transactive_channels, its about_node must be in transactive_nodes
        for tc in transactive_channels:
            if tc.about_node not in transactive_nodes:
                raise DcError(
                    f"Data channel {tc} has about_node {tc.about_node}, which does not have InPowerMetering!"
                )
        # Check condition 2: If a node is in transactive_nodes, there must be a data channel with that node as about_node
        for node in transactive_nodes:
            if not any(tc for tc in transactive_channels if tc.about_node == node):
                raise DcError(
                    f"Node {node} is in transactive_nodes but no data channel with InPowerMetering has this node as about_node"
                )

    @classmethod
    def check_ads_terminal_block_consistency(cls, c: Ads111xBasedComponent) -> None:
        possible_indices = set(
            range(1, c.cac.TotalTerminalBlocks + 1)
        )  # e,g {1, .., 12}
        actual_indices = {tc.TerminalBlockIdx for tc in c.gt.ConfigList}
        if not actual_indices.issubset(possible_indices):
            raise DcError(
                f"Terminal Block indices {actual_indices}"
                f"When Ads only has {c.cac.TotalTerminalBlocks} terminal blocks!"
            )

    @classmethod
    def load_data_channels(
        cls,
        layout: dict[Any, Any],
        nodes: dict[str, ShNode],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
    ) -> dict[str, DataChannel]:
        dcs = {}
        if errors is None:
            errors = []
        for dc_dict in layout.get("DataChannels", []):
            try:
                dc_name = dc_dict["Name"]
                dcs[dc_name] = cls.make_channel(dc_dict, nodes)
            except Exception as e:  # noqa: PERF203
                if raise_errors:
                    raise
                errors.append(LoadError("DataChannel", dc_dict, e))
        return dcs

    @classmethod
    def load_synth_channels(
        cls,
        layout: dict[Any, Any],
        nodes: dict[str, ShNode],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
    ) -> dict[str, SynthChannel]:
        synths = {}
        if errors is None:
            errors = []
        for d in layout.get("SynthChannels", []):
            try:
                name = d["Name"]
                synths[name] = cls.make_synth_channel(d, nodes)
            except Exception as e:  # noqa: PERF203
                if raise_errors:
                    raise
                errors.append(LoadError("SynthChannel", d, e))
        return synths

    @classmethod
    def resolve_node_links(
        cls,
        node: ShNode,
        all_nodes: dict[str, ShNode],
        components: dict[str, Component[Any, Any]],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
    ) -> None:
        if errors is None:
            errors = []
        try:
            if node.component_id is not None:
                component = components.get(node.component_id, None)
                if component is None:
                    raise DcError(  # noqa: TRY301
                        f"{node.name} component {node.component_id} not loaded!"
                    )
                if isinstance(component, ComponentResolver):
                    component.resolve(
                        node.name,
                        all_nodes,
                        components,
                    )
        except Exception as e:
            if raise_errors:
                raise
            errors.append(
                LoadError("ShNode", {"node": {"name": node.Name, "node": node}}, e)
            )

    @classmethod
    def resolve_links(
        cls,
        nodes: dict[str, ShNode],
        components: dict[str, Component[Any, Any]],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
    ) -> None:
        if errors is None:
            errors = []
        for node in nodes.values():
            cls.resolve_node_links(
                node=node,
                all_nodes=nodes,
                components=components,
                raise_errors=raise_errors,
                errors=errors,
            )

    def __init__(  # noqa: PLR0913
        self,
        layout: dict[Any, Any],
        *,
        cacs: dict[str, ComponentAttributeClassGt],
        components: dict[str, Component[Any, Any]],
        nodes: dict[str, ShNode],
        data_channels: dict[str, DataChannel],
        synth_channels: dict[str, SynthChannel],
    ) -> None:
        self.layout = copy.deepcopy(layout)
        self.cacs = dict(cacs)
        self.components = dict(components)
        self.components_by_type = defaultdict(list)
        for component in self.components.values():
            self.components_by_type[type(component)].append(component)
        self.nodes = dict(nodes)
        self.nodes_by_component = {
            node.component_id: node.name
            for node in self.nodes.values()
            if node.component_id is not None
        }
        self.data_channels = dict(data_channels)
        self.synth_channels = dict(synth_channels)

    def clear_property_cache(self) -> None:
        for cached_prop_name in [
            prop_name
            for prop_name in type(self).__dict__
            if isinstance(type(self).__dict__[prop_name], cached_property)
        ]:
            self.__dict__.pop(cached_prop_name, None)

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
    ) -> "HardwareLayout":
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

    @classmethod
    def validate_layout(  # noqa: C901
        cls,
        load_args: LoadArgs,
        *,
        raise_errors: bool,
        errors: Optional[list[LoadError]] = None,
    ) -> None:
        nodes = load_args["nodes"]
        components = load_args["components"]
        data_channels = load_args["data_channels"]
        errors_caught = []
        try:
            cls.check_node_unique_ids(nodes)
        except Exception as e:  # noqa: BLE001
            errors_caught.append(LoadError("hardware.layout", nodes, e))
        try:
            cls.check_handle_hierarchy(nodes)
        except Exception as e:
            if raise_errors:
                raise
            errors_caught.append(LoadError("hardware.layout", nodes, e))
        try:
            cls.check_actor_component_consistency(nodes)
        except Exception as e:  # noqa: BLE001
            errors_caught.append(LoadError("hardware.layout", nodes, e))
        try:
            cls.check_data_channel_consistency(
                nodes,
                components,
                data_channels,
            )
            cls.check_transactive_metering_consistency(
                nodes,
                data_channels,
            )
        except Exception as e:  # noqa: BLE001
            errors_caught.append(LoadError("data.channel.gt", data_channels, e))
        ads111x_components = [
            comp
            for comp in components.values()
            if isinstance(comp, Ads111xBasedComponent)
        ]
        for c in ads111x_components:
            try:
                cls.check_ads_terminal_block_consistency(c)
            except Exception as e:  # noqa: BLE001, PERF203
                errors_caught.append(
                    LoadError("ads111x.based.component.gt", c.gt.model_dump(), e)
                )
        if errors_caught:
            if raise_errors:
                s = "ERROR in HardwareLayout validation. Caught:\n"
                for error in errors_caught:
                    s += f"  TypeName: {error.type_name}  Exception: <{error.exception}>  src: {error.src_dict}\n"
                raise DcError(s)
            if errors is not None:
                errors.extend(errors_caught)

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
    ) -> "HardwareLayout":
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
        return HardwareLayout(layout, **load_args)

    def add_node(self, node: dict[str, Any] | SpaceheatNodeGt) -> ShNode:
        node = self.make_node(node, self.components)
        if node.Name in self.nodes:
            raise ValueError(f"ERROR. Node with name {node.Name} already exists")
        if node.ComponentId in self.nodes_by_component:
            raise ValueError(
                f"ERROR. Node with component id {node.ComponentId} "
                "already exists. "
                f"Tried to add node {node.Name}. Existing node is "
                f"{self.nodes_by_component[node.ComponentId]}"
            )
        self.nodes[node.Name] = node
        self.resolve_node_links(node, self.nodes, self.components, raise_errors=True)
        if node.ComponentId is not None:
            self.nodes_by_component[node.ComponentId] = node.Name
        self.clear_property_cache()
        return node

    def channel(self, name: str, default: Any = None) -> DataChannel:  # noqa: ANN401
        return self.data_channels.get(name, default)

    def synth_channel(self, name: str, default: Any = None) -> SynthChannel:  # noqa: ANN401
        return self.synth_channels.get(name, default)

    def node(self, name: str, default: Any = None) -> ShNode:  # noqa: ANN401
        return self.nodes.get(name, default)

    def node_by_handle(self, handle: str) -> Optional[ShNode]:
        d = {node.Handle: node for node in self.nodes.values() if node.Handle}
        if handle in d:
            return d[handle]
        return None

    def component(self, node_name: str) -> Optional[Component[Any, Any]]:
        return self.component_from_node(self.node(node_name, None))

    def cac(self, node_name: str) -> Optional[ComponentAttributeClassGt]:
        component = self.component(node_name)
        if component is None:
            return None
        return typing.cast(ComponentAttributeClassGt, component.cac)

    def get_component_as_type(self, component_id: str, type_: type[T]) -> Optional[T]:
        component = self.components.get(component_id, None)
        if component is not None and not isinstance(component, type_):
            raise ValueError(
                f"ERROR. Component <{component_id}> has type {type(component)} not {type_}"
            )
        return component

    def get_components_by_type(self, type_: type[T]) -> list[T]:
        entries = self.components_by_type.get(type_, [])
        for i, entry in enumerate(entries):
            if not isinstance(entry, type_):
                raise TypeError(
                    f"ERROR. Entry {i + 1} in "
                    f"HardwareLayout.components_by_typ[{type_}] "
                    f"has the wrong type {type(entry)}"
                )
        return typing.cast(list[T], entries)

    def node_from_component(self, component_id: str) -> Optional[ShNode]:
        return self.nodes.get(self.nodes_by_component.get(component_id, ""), None)

    def component_from_node(
        self, node: Optional[ShNode]
    ) -> Optional[Component[Any, Any]]:
        return (
            self.components.get(
                node.component_id if node.component_id is not None else "", None
            )
            if node is not None
            else None
        )

    @classmethod
    def parent_hierarchy_name(cls, hierarchy_name: str) -> Optional[str]:
        last_delimiter = hierarchy_name.rfind(".")
        if last_delimiter == -1:
            return None
        return hierarchy_name[:last_delimiter]

    def parent_node(self, node: ShNode) -> Optional[ShNode]:
        h_name = self.parent_hierarchy_name(node.actor_hierarchy_name)
        if not h_name:
            return None
        parent = next(
            (n for n in self.nodes.values() if n.actor_hierarchy_name == h_name), None
        )
        if parent is None:
            raise DcError(f"{node} is missing parent {h_name}!")
        return self.node(h_name)

    @classmethod
    def boss_handle(cls, handle: str) -> Optional[str]:
        if "." not in handle:
            return None
        return ".".join(handle.split(".")[:-1])

    def boss_node(self, node: ShNode) -> Optional[ShNode]:
        boss_handle = self.boss_handle(node.handle)
        # No dots in your name: you are your own boss
        if not boss_handle:
            return node
        boss = next((n for n in self.nodes.values() if n.handle == boss_handle), None)
        if boss is None:
            raise DcError(f"{node} is missing boss {boss_handle}")
        return boss

    def direct_reports(self, node: ShNode) -> list[ShNode]:
        return [n for n in self.nodes.values() if self.boss_node(n) == node]

    def node_from_handle(self, handle: str) -> Optional[ShNode]:
        return next((n for n in self.nodes.values() if n.handle == handle), None)

    @cached_property
    def atn_g_node_alias(self) -> str:
        return self.layout["MyAtomicTNodeGNode"]["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def atn_g_node_instance_id(self) -> str:
        return self.layout["MyAtomicTNodeGNode"]["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def atn_g_node_id(self) -> str:
        return self.layout["MyAtomicTNodeGNode"]["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def terminal_asset_g_node_alias(self) -> str:
        my_atn_as_dict = self.layout["MyTerminalAssetGNode"]
        return my_atn_as_dict["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def terminal_asset_g_node_id(self) -> str:
        my_atn_as_dict = self.layout["MyTerminalAssetGNode"]
        return my_atn_as_dict["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def scada_g_node_alias(self) -> str:
        my_scada_as_dict = self.layout["MyScadaGNode"]
        return my_scada_as_dict["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def scada_g_node_id(self) -> str:
        my_scada_as_dict = self.layout["MyScadaGNode"]
        return my_scada_as_dict["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def all_telemetry_tuples_for_agg_power_metering(self) -> list[TelemetryTuple]:
        telemetry_tuples = []
        for node in self.all_nodes_in_agg_power_metering:
            telemetry_tuples += [
                TelemetryTuple(
                    AboutNode=node,
                    SensorNode=self.power_meter_node,
                    TelemetryName=TelemetryName.PowerW,
                )
            ]
        return telemetry_tuples

    @cached_property
    def all_nodes_in_agg_power_metering(self) -> list[ShNode]:
        """All nodes whose power level is metered and included in power reporting by the Scada"""
        all_nodes = list(self.nodes.values())
        return list(filter(lambda x: x.in_power_metering, all_nodes))

    @cached_property
    def all_power_meter_telemetry_tuples(self) -> list[TelemetryTuple]:
        return [
            TelemetryTuple(
                AboutNode=self.nodes[
                    self.data_channels[config.ChannelName].AboutNodeName
                ],
                SensorNode=self.power_meter_node,
                TelemetryName=self.data_channels[config.ChannelName].TelemetryName,
            )
            for config in self.power_meter_component.gt.ConfigList
        ]

    @cached_property
    def power_meter_node(self) -> ShNode:
        return next(
            filter(lambda x: x.ActorClass == ActorClass.PowerMeter, self.nodes.values())
        )

    @cached_property
    def power_meter_component(self) -> ElectricMeterComponent:
        if self.power_meter_node.component is None:
            raise ValueError(
                f"ERROR. power_meter_node {self.power_meter_node} has no component."
            )
        return typing.cast(ElectricMeterComponent, self.power_meter_node.component)

    @cached_property
    def power_meter_cac(self) -> ElectricMeterCacGt:
        if isinstance(self.power_meter_component.cac, ElectricMeterCacGt):
            return self.power_meter_component.cac
        raise TypeError(
            f"ERROR. power_meter_component cac {self.power_meter_component.cac}"
            f" / {type(self.power_meter_component.cac)} is not an ElectricMeterCac"
        )

    @cached_property
    def all_multipurpose_telemetry_tuples(self) -> list[TelemetryTuple]:
        multi_nodes = list(
            filter(
                lambda x: (
                    x.actor_class
                    in {
                        ActorClass.MultipurposeSensor,
                        ActorClass.HubitatTankModule,
                        ActorClass.HubitatPoller,
                        ActorClass.HoneywellThermostat,
                    }
                ),
                self.nodes.values(),
            )
        )
        telemetry_tuples: list[TelemetryTuple] = []
        for node in multi_nodes:
            if node.component is not None and (
                channels := [
                    self.data_channels[cfg.ChannelName]
                    for cfg in node.component.gt.ConfigList
                ]
            ):
                telemetry_tuples.extend(
                    TelemetryTuple(
                        AboutNode=ch.about_node,
                        SensorNode=ch.captured_by_node,
                        TelemetryName=ch.TelemetryName,
                    )
                    for ch in channels
                )
        return telemetry_tuples

    @cached_property
    def my_telemetry_tuples(self) -> list[TelemetryTuple]:
        """This will include telemetry tuples from all the multipurpose sensors, the most
        important of which is the power meter."""
        return (
            self.all_power_meter_telemetry_tuples
            + self.all_multipurpose_telemetry_tuples
        )

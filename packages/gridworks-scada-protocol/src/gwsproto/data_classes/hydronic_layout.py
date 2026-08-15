import copy
import json
import typing
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, List, Optional, TypeVar

from gwsproto.errors import DcError
from gwsproto.decoders import (
    ComponentDecoder,
    DeviceTypeDecoder,
)
from gwsproto.default_decoders import (
    default_component_decoder,
    default_device_type_decoder,
)

import gwsproto.data_classes.components
from gwsproto.data_classes.components import Ads111xBasedComponent, Component
from gwsproto.data_classes.components.component import ComponentOnly
from gwsproto.data_classes.components.electric_meter_component import (
    ElectricMeterComponent,
)
from gwsproto.data_classes.components.scada_board_component import (
    ScadaBoardComponent,
)
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.resolver import ComponentResolver
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.data_classes.derived_channel import DerivedChannel

from gwsproto.enums import ActorClass, TelemetryName, Unit, EmissionMethod
from gwsproto.named_types import House0Layout as House0LayoutWord
from gwsproto.named_types import NolanLayout as NolanLayoutWord
from gwsproto.named_types import (
    CaptureTuning,
    DataChannelGt,
    ElectricMeterDeviceTypeGt,
    RequiredEnergyLayered,
    ScadaBoardComponentGt,
    SpaceheatNodeGt,
    UsableEnergyLayered,
)
from gwsproto.type_helpers.channel_named import ChannelNamed
from gwsproto.type_helpers.component_base import (
    BoardResidentComponentBase,
    ComponentBase,
    DeviceComponentBase,
)
from gwsproto.data_classes.components.web_server_component import WebServerComponent
from gwsproto.data_classes.house_0_names import H0CN, H0N, ScadaWeb
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types.hydronic import Hydronic
from gwsproto.enums import FlowManifoldVariant
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.hydronic_spaceheat.node_names import (
    HydronicSpaceheatNodeNames as HSNN,
)
from gwsproto.names.nolan.node_names import NolanNodeNames
from enum import Enum


@dataclass
class LoadError:
    type_name: str
    src_dict: dict[Any, Any]
    exception: Exception


class LoadArgs(typing.TypedDict):
    device_types: dict[str, Any]
    components: dict[str, Component[Any, Any]]
    nodes: dict[str, ShNode]
    data_channels: dict[str, DataChannel]
    derived_channels: dict[str, DerivedChannel]


class ChannelRegistry:
    def __init__(
        self,
        *,
        data_channels: dict[str, DataChannel],
        derived_channels: dict[str, DerivedChannel],
    ):
        self.data = data_channels
        self.derived = derived_channels

    def get(self, name: str) -> DataChannel | DerivedChannel | None:
        return self.data.get(name) or self.derived.get(name)

    def unit(self, name: str) -> Unit | TelemetryName | None:
        ch = self.get(name)
        if ch is None:
            return None
        if isinstance(ch, DataChannel):
            return ch.TelemetryName
        if isinstance(ch, DerivedChannel):
            return ch.OutputUnit
        return None


# A sema word carries its own TypeName; ask the class rather than keeping a
# second copy of the string that can drift from it.
HOUSE0_LAYOUT_TYPE_NAME = House0LayoutWord.type_name_value()
NOLAN_LAYOUT_TYPE_NAME = NolanLayoutWord.type_name_value()


class LayoutBucket(str, Enum): 
    ADS111X = "Ads111xBased"
    ELECTRIC_METER = "ElectricMeter"
    OTHER = "Other"

    @property
    def device_type_list_name(self) -> str:
        """The single device-type record bucket."""
        return "DeviceTypes"

    @property
    def component_list_name(self) -> str:
        """e.g. OtherComponents"""
        return f"{self.value}Components"

class House0LoadArgs(LoadArgs):
    flow_manifold_variant: FlowManifoldVariant
    use_sieg_loop: bool

class HouseStrategy(str, Enum):
    House0 = "House0"
    Nolan = "Nolan"


T = TypeVar("T")


class HydronicLayout:
    layout: dict[Any, Any]
    device_types: dict[str, Any]
    components: dict[str, Component[Any, Any]]
    components_by_type: dict[type[Any], list[Component[Any, Any]]]
    nodes: dict[str, ShNode]
    nodes_by_component: dict[str, str]

    GT_SUFFIX = "Gt"

    @classmethod
    def load_device_types(
        cls,
        layout: dict[str, Any],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        device_type_decoder: Optional[DeviceTypeDecoder] = None,
    ) -> dict[str, Any]:
        if errors is None:
            errors = []
        if device_type_decoder is None:
            device_type_decoder = default_device_type_decoder
        device_types: dict[str, Any] = {}
        for dt_dict in layout.get("DeviceTypes", ()):
            try:
                dt = device_type_decoder.decode(dt_dict)
                device_types[dt.DeviceType] = dt
            except Exception as e:  # noqa: PERF203
                if raise_errors:
                    raise
                errors.append(LoadError("DeviceTypes", dt_dict, e))
        return device_types

    @classmethod
    def get_data_class_name(cls, component_gt: ComponentBase) -> str:
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
        cls, component_gt: ComponentBase
    ) -> type[Component[Any, Any]]:
        return getattr(
            gwsproto.data_classes.components,
            cls.get_data_class_name(component_gt),
            ComponentOnly,
        )

    @classmethod
    def make_component(
        cls,
        component_gt: ComponentBase,
        device_type: Optional[Any] = None,
        **kwargs: Any,
    ) -> Component[Any, Any]:
        return cls.get_data_class_class(component_gt)(
            gt=component_gt, device_type=device_type, **kwargs
        )

    @classmethod
    def load_components(
        cls,
        layout: dict[Any, Any],
        device_types: dict[str, Any],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> dict[str, Component[Any, Any]]:
        if errors is None:
            errors = []
        if component_decoder is None:
            component_decoder = default_component_decoder
        decoded: list[tuple[str, dict[Any, Any], ComponentBase]] = []
        for type_name in [
            "Ads111xBasedComponents",
            "ElectricMeterComponents",
            "OtherComponents",
        ]:
            for component_dict in layout.get(type_name, ()):
                try:
                    decoded.append(
                        (type_name, component_dict, component_decoder.decode(component_dict))
                    )
                except Exception as e:  # noqa: PERF203
                    if raise_errors:
                        raise
                    errors.append(LoadError(type_name, component_dict, e))

        components: dict[str, Component[Any, Any]] = {}
        # Boards first: a board-resident component is constructed WITH its
        # resolved board, so board_component is never in a half-set state.
        board_gts = [t for t in decoded if isinstance(t[2], ScadaBoardComponentGt)]
        for type_name, component_dict, component_gt in board_gts + [
            t for t in decoded if not isinstance(t[2], ScadaBoardComponentGt)
        ]:
            try:
                # Join by the readable DeviceType. The specialized device-type record is
                # OPTIONAL — only device categories carrying category-level data open one
                # (electric.meter / ads111x / gw1.scada). A record-less category (web
                # server, hubitat, sim) resolves to None. The layout's DeviceTypeMembership
                # axiom is what guarantees a record IS present when a category needs it.
                # Board-resident components carry no DeviceType (they anchor to a
                # board via BoardComponentId); their device_type resolves to None here.
                device_type_gt = None
                if isinstance(component_gt, DeviceComponentBase):
                    device_type_gt = device_types.get(component_gt.DeviceType)
                kwargs: dict[str, Any] = {}
                if isinstance(component_gt, BoardResidentComponentBase):
                    board = components.get(component_gt.BoardComponentId)
                    if not isinstance(board, ScadaBoardComponent):
                        raise DcError(  # noqa: TRY301
                            f"Component <{component_gt.ComponentId}> anchors to board "
                            f"<{component_gt.BoardComponentId}>, which is "
                            + (
                                "not loaded"
                                if board is None
                                else "not a ScadaBoardComponent"
                            )
                        )
                    kwargs["board_component"] = board
                components[component_gt.ComponentId] = cls.make_component(
                    component_gt,
                    device_type_gt,
                    **kwargs,
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
            try:
                node_gt = SpaceheatNodeGt.model_validate(node_dict)
            except Exception as e:
                raise Exception(f"trouble wi {node_dict}: {e}")
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
    def make_derived_channel(
        cls,
        derived_dict: dict[str, Any],
        nodes: dict[str, ShNode],
    ) -> DerivedChannel:
        created_by_node_name = derived_dict.get("CreatedByNodeName", "")
        created_by_node = nodes.get(created_by_node_name)

        if created_by_node is None:
            raise ValueError(
                f"ERROR. DerivedChannel related nodes must exist for "
                f"{derived_dict.get('Name')}!\n"
                f"  For CreatedByNodeName<{created_by_node_name}> got None!\n"
            )

        try:
            d = DerivedChannel(
                created_by_node=created_by_node,
                **derived_dict,
            )
        except Exception as e:
            raise Exception(f" trouble with {derived_dict}: {e}")

        return d

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
            # Only channel-named configs reference data channels; e.g.
            # i2c.dac.channel.config entries carry power-on defaults, not
            # captures, and have no ChannelName at all. Bare components (no
            # sema ConfigList at all, e.g. pico.btu.meter.component.gt) have
            # no attribute here — their channels bind via
            # DataChannel.CapturedByNodeName only.
            channel_names = {
                config.ChannelName
                for config in getattr(c.gt, "ConfigList", None) or []
                if isinstance(config, ChannelNamed)
            }
            if dc_names_by_component & channel_names:
                raise DcError(
                    f"Channel name overlap!: {dc_names_by_component & channel_names}"
                )
            dc_names_by_component.update(channel_names)
        # Component ConfigList references must be a SUBSET of the declared
        # DataChannels. NOT a bijection: a declared channel with no ConfigList
        # entry is fine (e.g. sim components carry no ConfigList; their channels
        # bind via DataChannel.CapturedByNodeName, the sole channel→node binding).
        actual_dc_names = {dc.Name for dc in data_channels.values()}
        referenced_not_declared = sorted(dc_names_by_component - actual_dc_names)
        if referenced_not_declared:
            raise DcError(
                f"Referenced by components but missing from DataChannels: "
                f"{referenced_not_declared}"
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
        cls,
        data_channels: dict[str, DataChannel],
        derived_channels: dict[str, DerivedChannel],
    ) -> None:
        """Transactive-power singularity + boundary binding.

        The layout SHALL carry exactly one DerivedChannel with
        Strategy "transactive-power". Its InputChannelNames are the metered
        channels (the transactive boundary): each SHALL resolve to an existing
        DataChannel whose about_node carries a NameplatePowerW. This replaces
        the old per-node/per-channel InPowerMetering flags — the metered set is
        now declared once, by the transactive-power DerivedChannel's inputs.
        """
        transactive = [
            d for d in derived_channels.values()
            if d.Strategy == "transactive-power"
        ]
        if len(transactive) != 1:
            raise DcError(
                "Layout SHALL have exactly one transactive-power DerivedChannel; "
                f"found {len(transactive)}"
            )
        dc = transactive[0]
        for name in dc.InputChannelNames:
            ch = data_channels.get(name)
            if ch is None:
                raise DcError(
                    f"transactive-power DerivedChannel '{dc.Name}' input '{name}' "
                    "is not a known DataChannel"
                )
            if ch.about_node.NameplatePowerW is None:
                raise DcError(
                    f"transactive-power input '{name}' has about_node "
                    f"'{ch.about_node.Name}' with no NameplatePowerW"
                )

    @classmethod
    def check_ads_terminal_block_consistency(cls, c: Ads111xBasedComponent) -> None:
        possible_indices = set(
            range(1, c.device_type.TotalTerminalBlocks + 1)
        )  # e,g {1, .., 12}
        actual_indices = {tc.TerminalBlockIdx for tc in c.gt.ConfigList}
        if not actual_indices.issubset(possible_indices):
            raise DcError(
                f"Terminal Block indices {actual_indices}"
                f"When Ads only has {c.device_type.TotalTerminalBlocks} terminal blocks!"
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
    def load_derived_channels(
        cls,
        layout: dict[Any, Any],
        nodes: dict[str, ShNode],
        *,
        raise_errors: bool = True,
        errors: Optional[list[LoadError]] = None,
    ) -> dict[str, DerivedChannel]:
        derived: dict[str, DerivedChannel] = {}

        if errors is None:
            errors = []

        for d in layout.get("DerivedChannels", []):
            try:
                name = d["Name"]
                derived[name] = cls.make_derived_channel(d, nodes)
            except Exception as e:  # noqa: PERF203
                if raise_errors:
                    raise
                errors.append(LoadError("DerivedChannel", d, e))

        return derived

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
        device_types: dict[str, Any],  # by DeviceType
        components: dict[str, Component],  # by id
        nodes: dict[str, ShNode],  # by name
        data_channels: dict[str, DataChannel],  # by name
        derived_channels: dict[str, DerivedChannel],
        flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0,
        use_sieg_loop: bool = False,
    ) -> None:
        self.layout = copy.deepcopy(layout)
        self.capture_tuning_by_channel: dict[str, CaptureTuning] = {
            ct["ChannelName"]: CaptureTuning.model_validate(ct)
            for ct in self.layout.get("CaptureTuningList", [])
        }
        self.device_types = dict(device_types)
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
        self.derived_channels = dict(derived_channels)
        self.validate_derived_channels()

        self.derived_channels = self.load_derived_channels(layout, self.nodes)

        # ---- Hydronic block (the gw.hydronic type lives on the dataclass) ----
        # Accept the typed nested "Hydronic" if present; else build it from the legacy
        # flat top-level keys (transitional, while the fixtures migrate).
        self.hydronic = self._build_hydronic(
            layout, self.derived_channels, flow_manifold_variant, use_sieg_loop
        )
        # Flat accessors derived from the typed hydronic (actor code reads these).
        self.zone_list = [z.Name for z in self.hydronic.Zones]
        self.critical_zone_list = [z.Name for z in self.hydronic.Zones if z.Critical]
        self.zone_kwh_per_deg_f_list = [z.KwhPerDegF for z in self.hydronic.Zones]
        self.total_store_tanks = self.hydronic.TotalStoreTanks
        self.use_sieg_loop = self.hydronic.UseSiegLoop
        self.flow_manifold_variant = (
            FlowManifoldVariant.House0Sieg
            if self.hydronic.SiegLoopPlumbed
            else FlowManifoldVariant.House0
        )
        if not 1 <= self.total_store_tanks <= 6:
            raise ValueError("Must have between 1 and 6 store tanks")
        if not 1 <= len(self.zone_list) <= 6:
            raise ValueError("Must have between 1 and 6 store zones")
        self.h0n = H0N(self.total_store_tanks, self.zone_list)
        self.h0cn = H0CN(self.total_store_tanks, self.zone_list)
        web_servers = {
            ws.web_server_gt.Name
            for ws in self.get_components_by_type(WebServerComponent)
        }

        if ScadaWeb.DEFAULT_SERVER_NAME not in web_servers:
            raise ValueError(
                f"HydronicLayout requires a WebServerComponent named "
                f"'{ScadaWeb.DEFAULT_SERVER_NAME}'"
            )

        self.validate_tank_temp_calibration_consistency()
        self.validate_house0_system_models()

    def validate_api_tank_module_wiring(self) -> None:
        errors: list[str] = []

        for node in self.nodes.values():
            if node.ActorClass != ActorClass.ApiTankModule:
                continue

            for depth in (1, 2, 3):
                ch = f"{node.Name}-depth{depth}-device"
                dc = self.data_channels.get(ch)
                if dc is None:
                    errors.append(
                        f"ApiTankModule '{node.Name}' missing DataChannel '{ch}'"
                    )
                elif dc.gt.CapturedBy != node.Name:
                    errors.append(
                        f"DataChannel '{ch}' must be captured by '{node.Name}'"
                    )

        if errors:
            raise DcError(
                "ApiTankModule wiring validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    def validate_derived_channels(self) -> None:
        """
        Validate GridWorks-specific semantic constraints for DerivedChannelGt.

        This enforces:
        - All InputChannelNames reference existing DataChannels
        - Strategy-specific requirements on inputs, parameters, and emission method
        """
        data_channel_names = set(self.data_channels.keys())
        derived_channel_names = set(self.derived_channels.keys())
        errors: list[str] = []

        # --- Input channel existence ---
        for dc in self.derived_channels.values():
            for input_name in dc.InputChannelNames:
                if (
                    input_name not in data_channel_names
                    and input_name not in derived_channel_names
                ):
                    errors.append(
                        f"DerivedChannel '{dc.Name}' references unknown input "
                        f"channel '{input_name}'"
                    )

            match dc.Strategy:
                case "identity":
                    if len(dc.InputChannelNames) != 1:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'identity' "
                            "but does not declare exactly one InputChannelName"
                        )
                    if dc.EmissionMethod != EmissionMethod.OnTrigger:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'identity' "
                            "but must use EmissionMethod.OnTrigger"
                        )

                case "affine":
                    if len(dc.InputChannelNames) != 1:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'affine' "
                            "but does not declare exactly one InputChannelName"
                        )
                    if not dc.Parameters or "Calibration" not in dc.Parameters:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'affine' "
                            "but is missing Parameters.Calibration"
                        )
                    if dc.EmissionMethod != EmissionMethod.OnTrigger:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'affine' "
                            "but must use EmissionMethod.OnTrigger"
                        )

                case "heat-call":
                    if len(dc.InputChannelNames) != 1:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'heat-call' "
                            "but does not declare exactly one InputChannelName"
                        )
                    if not dc.Parameters or "Interpretation" not in dc.Parameters:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'heat-call' "
                            "but is missing Parameters.Interpretation"
                        )
                    if dc.EmissionMethod != EmissionMethod.AsyncAndPeriodic:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'heat-call' "
                            "but must use EmissionMethod.AsyncAndPeriodic"
                        )

                case "simple-falling-edge-setpoint":
                    if len(dc.InputChannelNames) != 2:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'simple-falling-edge-setpoint' but does not declare "
                            "exactly two InputChannelNames: [gw-temp, heat-call]"
                        )
                    elif dc.InputChannelNames[0] not in data_channel_names:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'simple-falling-edge-setpoint' but its first "
                            f"InputChannelName '{dc.InputChannelNames[0]}' is not a "
                            "known DataChannel"
                        )
                    else:
                        heat_call_name = dc.InputChannelNames[1]
                        heat_call_dc = self.derived_channels.get(heat_call_name)
                        if heat_call_dc is None:
                            errors.append(
                                f"DerivedChannel '{dc.Name}' uses strategy "
                                "'simple-falling-edge-setpoint' but its second "
                                f"InputChannelName '{heat_call_name}' is not a "
                                "known DerivedChannel"
                            )
                        elif heat_call_dc.Strategy != "heat-call":
                            errors.append(
                                f"DerivedChannel '{dc.Name}' uses strategy "
                                "'simple-falling-edge-setpoint' but its second "
                                f"InputChannelName '{heat_call_name}' must reference "
                                "a DerivedChannel with strategy 'heat-call'"
                            )
                    if dc.OutputUnit != Unit.FahrenheitX100:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'simple-falling-edge-setpoint' but must use OutputUnit "
                            "FahrenheitX100"
                        )
                    if dc.EmissionMethod != EmissionMethod.AsyncAndPeriodic:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'simple-falling-edge-setpoint' but must use "
                            "EmissionMethod.AsyncAndPeriodic"
                        )
                    if not dc.Parameters:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'simple-falling-edge-setpoint' but is missing Parameters"
                        )
                    else:
                        threshold = dc.Parameters.get("SetpointThresholdFX100")
                        if (
                            not isinstance(threshold, int)
                            or isinstance(threshold, bool)
                            or threshold <= 0
                        ):
                            errors.append(
                                f"DerivedChannel '{dc.Name}' uses strategy "
                                "'simple-falling-edge-setpoint' but Parameters."
                                "SetpointThresholdFX100 is missing or not a "
                                "positive integer"
                            )

                case "system-model":
                    if dc.InputChannelNames:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy '{dc.Strategy}' "
                            "but must not declare InputChannelNames"
                        )
                    if dc.EmissionMethod != EmissionMethod.Periodic:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy '{dc.Strategy}' "
                            "but must use EmissionMethod.Periodic"
                        )

                case "sum":
                    # e.g. maple's derived primary-flow = sieg-send + sieg-flow.
                    if len(dc.InputChannelNames) < 2:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'sum' but must "
                            "declare at least two InputChannelNames"
                        )
                    if dc.EmissionMethod != EmissionMethod.OnTrigger:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy 'sum' but must "
                            "use EmissionMethod.OnTrigger"
                        )

                case "transactive-power":
                    # Produced by the power-meter actor (not derived-generator).
                    # Its inputs are the metered PowerW channels (the transactive
                    # boundary); layout-level singularity + nameplate binding is
                    # enforced by check_transactive_metering_consistency.
                    if not dc.InputChannelNames:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'transactive-power' but declares no InputChannelNames"
                        )
                    if dc.OutputUnit != Unit.Watts:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'transactive-power' but must use OutputUnit Watts"
                        )
                    if dc.EmissionMethod != EmissionMethod.OnTrigger:
                        errors.append(
                            f"DerivedChannel '{dc.Name}' uses strategy "
                            "'transactive-power' but must use EmissionMethod.OnTrigger"
                        )

                case "integrate-relay-motion":
                    # Produced by the SiegLoop actor (not derived-generator); no
                    # derived-generator-side validation here.
                    pass

                case _:
                    errors.append(
                        f"DerivedChannel '{dc.Name}' uses unsupported strategy "
                        f"'{dc.Strategy}'"
                    )

        if errors:
            raise ValueError(
                "DerivedChannel input validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


    @cached_property
    def channel_registry(self) -> ChannelRegistry:
        return ChannelRegistry(
            data_channels=self.data_channels,
            derived_channels=self.derived_channels,
        )

    def clear_property_cache(self) -> None:
        for cached_prop_name in [
            prop_name
            for prop_name in type(self).__dict__
            if isinstance(type(self).__dict__[prop_name], cached_property)
        ]:
            self.__dict__.pop(cached_prop_name, None)

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
        derived_channels = load_args["derived_channels"]
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
                data_channels,
                derived_channels,
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
                s = "ERROR in HydronicLayout validation. Caught:\n"
                for error in errors_caught:
                    s += f"  TypeName: {error.type_name}  Exception: <{error.exception}>  src: {error.src_dict}\n"
                raise DcError(s)
            if errors is not None:
                errors.extend(errors_caught)

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

    def channel(self, name: str, default: Any = None) -> DataChannel | None:  # noqa: ANN401
        return self.data_channels.get(name, default)

    def derived_channel(self, name: str, default: Any = None) -> DerivedChannel | None:  # noqa: ANN401
        return self.derived_channels.get(name, default)

    def node(self, name: str, default: Any = None) -> ShNode | None:  # noqa: ANN401
        return self.nodes.get(name, default)

    def node_by_handle(self, handle: str) -> Optional[ShNode]:
        d = {node.Handle: node for node in self.nodes.values() if node.Handle}
        if handle in d:
            return d[handle]
        return None

    def component(self, node_name: str) -> Optional[Component[Any, Any]]:
        return self.component_from_node(self.node(node_name, None))

    def device_type(self, node_name: str) -> Optional[Any]:
        component = self.component(node_name)
        if component is None:
            return None
        return component.device_type

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
                    f"HydronicLayout.components_by_typ[{type_}] "
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
    def ltn_g_node_alias(self) -> str:
        return self.layout["MyLeafTransactiveNodeGNode"]["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def ltn_g_node_instance_id(self) -> str:
        return self.layout["MyLeafTransactiveNodeGNode"]["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def ltn_g_node_id(self) -> str:
        return self.layout["MyLeafTransactiveNodeGNode"]["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def terminal_asset_g_node_alias(self) -> str:
        d = self.layout["MyTerminalAssetGNode"]
        return d["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def terminal_asset_g_node_id(self) -> str:
        d = self.layout["MyTerminalAssetGNode"]
        return d["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def scada_g_node_alias(self) -> str:
        my_scada_as_dict = self.layout["MyScadaGNode"]
        return my_scada_as_dict["Alias"]  # type: ignore[no-any-return]

    @cached_property
    def scada_g_node_id(self) -> str:
        my_scada_as_dict = self.layout["MyScadaGNode"]
        return my_scada_as_dict["GNodeId"]  # type: ignore[no-any-return]

    @cached_property
    def all_nodes_in_agg_power_metering(self) -> list[ShNode]:
        """All nodes whose power is metered and included in power reporting by the
        Scada — the about-nodes of the transactive-power DerivedChannel's inputs
        (the metered set is declared once, by that channel)."""
        metered_nodes = []
        for dc in self.derived_channels.values():
            if dc.Strategy == "transactive-power":
                metered_nodes += [
                    self.data_channels[name].about_node
                    for name in dc.InputChannelNames
                ]
        return metered_nodes

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
    def power_meter_device_type(self) -> ElectricMeterDeviceTypeGt:
        if isinstance(self.power_meter_component.device_type, ElectricMeterDeviceTypeGt):
            return self.power_meter_component.device_type
        raise TypeError(
            f"ERROR. power_meter_component device_type {self.power_meter_component.device_type}"
            f" / {type(self.power_meter_component.device_type)} is not an ElectricMeterDeviceType"
        )
    def validate_tank_temp_calibration_consistency(self) -> None:
        """Each tank depth SHALL have a well-formed calibrated derived channel.

        The calibration now lives in the derived channel itself (Strategy
        `identity`, or `affine` with a `linear.one.dimensional.calibration` in
        Parameters) — there is no separate layout-level TankTempCalibrationMap to
        cross-check against. Affine well-formedness (the embedded Calibration) is
        validated by the base `validate_derived_channels`; here we require that the
        per-depth channel exists and uses an allowed strategy.
        """
        errors: list[str] = []
        depth_names = [f"buffer-depth{d}" for d in (1, 2, 3)]
        for tank_idx in range(1, self.total_store_tanks + 1):
            depth_names += [f"tank{tank_idx}-depth{d}" for d in (1, 2, 3)]

        for name in depth_names:
            dc = self.derived_channels.get(name)
            if dc is None:
                errors.append(f"Missing calibrated derived channel '{name}'")
            elif dc.Strategy not in ("identity", "affine"):
                errors.append(
                    f"DerivedChannel '{name}' must use identity or affine, "
                    f"got '{dc.Strategy}'"
                )

        if errors:
            raise DcError(
                "Tank temperature calibration:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    def validate_house0_system_models(self) -> None:
        """
        Enforce that the House0 layout defines exactly two valid system-model
        derived channels: usable energy and required energy.
        """

        required_channels = {
            H0CN.usable_energy,
            H0CN.required_energy,
        }

        # --- 1. Required channels exist ---
        missing = [
            name for name in required_channels
            if name not in self.derived_channels
        ]
        if missing:
            raise ValueError(
                "House0 layout is missing required system-model derived channels:\n"
                + "\n".join(missing)
            )

        allowed_models = {
            UsableEnergyLayered.type_name_value(),
            RequiredEnergyLayered.type_name_value(),
        }

        seen_models: set[str] = set()

        # --- 2. Validate each required channel ---
        for name in required_channels:
            dc = self.derived_channels[name]

            if dc.CreatedByNodeName != "derived-generator":
                raise ValueError(
                    f"{name} must be created by derived-generator "
                    f"(got {dc.CreatedByNodeName})"
                )

            if dc.Strategy != "system-model":
                raise ValueError(
                    f"{name} must use Strategy 'system-model' "
                    f"(got {dc.Strategy})"
                )

            if not dc.Parameters:
                raise ValueError(
                    f"{name} is missing Parameters"
                )

            model = dc.Parameters.get("EnergyModel")
            if not model:
                raise ValueError(
                    f"{name} is missing Parameters.EnergyModel"
                )

            type_name = model.get("TypeName")
            if not type_name:
                raise ValueError(
                    f"{name} EnergyModel is missing TypeName"
                )

            if type_name not in allowed_models:
                raise ValueError(
                    f"{name} has unsupported EnergyModel TypeName '{type_name}'"
                )

            seen_models.add(type_name)

        # --- 3. Exactly one of each model ---
        if seen_models != allowed_models:
            raise ValueError(
                "House0 layout must include exactly one usable-energy model "
                "and one required-energy model"
            )


    @property
    def unreported_channels(self) -> set[str]:
        """
        Channels that must exist in the layout but are NOT reported upstream.
        """
        # Example: exclude all device-level temperature channels
        # (kept locally for diagnostics and derived generation)
        # unreported: set[str] = set()

        # # Buffer device channels
        # unreported |= self.h0cn.buffer.device

        # # Tank device channels
        # for tank in self.h0cn.tank.values():
        #     unreported |= tank.device

        # return unreported

        return set()

    @property
    def tank_device_temp_channels(self) -> set[str]:
        channels = set(self.h0cn.buffer.devices)
        for tank in self.h0cn.tank.values():
            channels |= tank.devices
        return channels


    @classmethod
    def validate_house0(  # noqa: C901
        cls,
        load_args: House0LoadArgs,
        *,
        raise_errors: bool,
        errors: Optional[list[LoadError]] = None,
    ) -> None:
        nodes = load_args["nodes"]
        components = load_args["components"]
        data_channels = load_args["data_channels"]
        errors_caught = []

        # Check for essential nodes that must always exist
        essential_nodes = [
            H0N.ltn,
            H0N.primary_scada,
            H0N.leaf_ally,
            H0N.local_control,
            H0N.derived_generator,
            # H0N.relay_multiplexer,
            # H0N.vdc_relay,
            # H0N.tstat_common_relay,
            # H0N.store_charge_discharge_relay,
            # H0N.thermistor_common_relay,
            # H0N.aquastat_ctrl_relay,
            # H0N.store_pump_failsafe,
            # H0N.primary_pump_scada_ops,
            # H0N.primary_pump_failsafe
        ]


        # Add pico_cycler if there are any pico-based actors
        pico_actor_classes = [ActorClass.ApiFlowModule, ActorClass.ApiTankModule, ActorClass.ApiBtuMeter]
        has_pico_actors = any(
            node.actor_class in pico_actor_classes
            for node in nodes.values()
        )
        # if has_pico_actors:
        #     essential_nodes.append(H0N.pico_cycler)
        #     essential_nodes.append(H0N.vdc_relay)  # Also needed for pico cycling

        # Check for missing essential nodes
        missing_nodes = []
        for node_name in essential_nodes:
            if node_name not in nodes:
                missing_nodes.append(node_name)


        if missing_nodes:
            error_msg = f"Missing essential nodes in layout: {', '.join(missing_nodes)}"
            if has_pico_actors and H0N.pico_cycler in missing_nodes:
                error_msg += "\nNote: pico_cycler is required because layout contains pico-based actors"

            if raise_errors:
                raise DcError(error_msg)
            if errors is not None:
                errors_caught.append(LoadError("HydronicLayout", {"missing_nodes": missing_nodes}, DcError(error_msg)))
                
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

    @staticmethod
    def _build_hydronic(
        layout: dict,
        derived_channels: dict,
        flow_manifold_variant: FlowManifoldVariant,
        use_sieg_loop: bool,
    ) -> Hydronic:
        """The typed gw.hydronic for this layout: read the nested 'Hydronic'
        block if present, else build it from the legacy flat top-level keys
        (transitional, while the fixtures migrate to the nested block)."""
        h = layout.get("Hydronic")
        if isinstance(h, dict) and "Zones" in h:
            return Hydronic.model_validate(h)
        for key in ("ZoneList", "CriticalZoneList", "TotalStoreTanks", "ZoneKwhPerDegFList"):
            if key not in layout:
                raise DcError(f"House0 requires {key} (or a typed Hydronic block)!")
        critical = set(layout["CriticalZoneList"])
        # PrimaryFlowSource follows the actual primary-flow channel: a `sum`
        # DerivedChannel => DerivedSiegSum; otherwise Measured (a DataChannel).
        primary_derived = any(
            d.Name == "primary-flow" and d.Strategy == "sum"
            for d in derived_channels.values()
        )
        return Hydronic(
            Zones=[
                HvacZone(Name=name, Critical=name in critical, KwhPerDegF=float(kwh))
                for name, kwh in zip(layout["ZoneList"], layout["ZoneKwhPerDegFList"])
            ],
            TotalStoreTanks=layout["TotalStoreTanks"],
            UseSiegLoop=use_sieg_loop,
            SiegLoopPlumbed=flow_manifold_variant == FlowManifoldVariant.House0Sieg,
            PrimaryFlowSource="DerivedSiegSum" if primary_derived else "Measured",
            Strategy=layout.get("Strategy", "House0"),
        )

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
            raise DcError("Need a SiegLoop actor when using sieg loop!")
        sieg_loop = nodes[H0N.sieg_loop]
        if sieg_loop.actor_class != ActorClass.SiegLoop:
            raise DcError(f"SiegLoop actor {sieg_loop.name} shoud have actor class SiegLoop, not {sieg_loop.actor_class}")
        if H0N.hp_boss not in nodes.keys():
            raise DcError("Need HpBoss actor when using sieg loop!")
        hp_boss = nodes[H0N.hp_boss]
        if hp_boss.actor_class != ActorClass.HpBoss:
            raise DcError(f"HpBoss actor {hp_boss.name} shoud have actor class HpBoss, not {hp_boss.actor_class}")

    @classmethod
    def check_actors_when_not_using_sieg_loop(cls, nodes: dict[str, ShNode]) -> None:
        if H0N.sieg_loop in nodes.keys():
            raise DcError(f"If not using sieg loop, should not have node {H0N.sieg_loop}!")

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
        device_type_decoder: Optional[DeviceTypeDecoder] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> "HydronicLayout":
        with Path(layout_path).open() as f:
            layout = json.loads(f.read())
        return cls.load_dict(
            layout,
            included_node_names=included_node_names,
            raise_errors=raise_errors,
            errors=errors,
            device_type_decoder=device_type_decoder,
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
        device_type_decoder: Optional[DeviceTypeDecoder] = None,
        component_decoder: Optional[ComponentDecoder] = None,
    ) -> "HydronicLayout":
        if errors is None:
            errors = []
        device_types = cls.load_device_types(
            layout=layout,
            raise_errors=raise_errors,
            errors=errors,
            device_type_decoder=device_type_decoder,
        )
        components = cls.load_components(
            layout=layout,
            device_types=device_types,
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
        derived_channels = cls.load_derived_channels(
            layout=layout,
            nodes=nodes,
            raise_errors=raise_errors,
            errors=errors,
        )
        # Read the sieg topology from the typed Hydronic block if present, else
        # from the legacy flat top-level keys (transitional).
        _hyd = layout.get("Hydronic")
        if isinstance(_hyd, dict) and "Zones" in _hyd:
            _fmv = (
                FlowManifoldVariant.House0Sieg
                if _hyd.get("SiegLoopPlumbed")
                else FlowManifoldVariant.House0
            )
            _usl = bool(_hyd.get("UseSiegLoop", False))
        else:
            _fmv = FlowManifoldVariant(layout.get("FlowManifoldVariant", "House0"))
            _usl = bool(layout.get("UseSiegLoop", False))
        load_args: House0LoadArgs = {
            "device_types": device_types,
            "components": components,
            "nodes": nodes,
            "data_channels": data_channels,
            "derived_channels": derived_channels,
            "flow_manifold_variant": _fmv,
            "use_sieg_loop": _usl,
        }
        cls.resolve_links(
            load_args["nodes"],
            load_args["components"],
            raise_errors=raise_errors,
            errors=errors,
        )
        cls.validate_layout(load_args, raise_errors=raise_errors, errors=errors)
        cls.validate_house0(load_args, raise_errors=raise_errors, errors=errors)
        return HydronicLayout(layout, **load_args)


    @property
    def primary_scada(self) -> ShNode:
        n = self.node(H0N.primary_scada)
        if n is None:
            raise Exception(f"{H0N.primary_scada} is known to exist")
        return n

    @property
    def derived_generator(self) -> ShNode:
        n = self.node(H0N.derived_generator)
        if n is None:
            raise Exception(f"{H0N.derived_generator} is known to exist")
        return n
    
    @property
    def local_control(self) -> ShNode:
        n = self.node(H0N.local_control)
        if n is None:
            raise Exception(f"{H0N.local_control} is known to exist")
        return n
    
    @property
    def auto_node(self) -> ShNode:
        n = self.node(H0N.auto)
        if n is None:
            raise Exception(f"{H0N.auto} is known to exist")
        return n

    @property
    def local_control_normal_node(self) -> ShNode:
        n = self.node(H0N.local_control_normal)
        if n is None:
            raise Exception(f"{H0N.local_control_normal} is known to exist")
        return n

    @property
    def local_control_backup_node(self) -> ShNode:
        n = self.node(H0N.local_control_backup)
        if n is None:
            raise Exception(f"{H0N.local_control_backup} is known to exist")
        return n

    @property
    def local_control_scada_blind_node(self) -> ShNode:
        n = self.node(H0N.local_control_scada_blind)
        if n is None:
            raise Exception(f"{H0N.local_control_scada_blind} is known to exist")
        return n
    
    @property
    def hp_boss(self) -> ShNode:
        n = self.node(H0N.hp_boss)
        if n is None:
            raise Exception(f"{H0N.hp_boss} is known to exist")
        return n
    
    @property
    def leaf_ally(self) -> ShNode:
        n = self.node(H0N.leaf_ally)
        if n is None:
            raise Exception(f"{H0N.leaf_ally} is known to exist")
        return n
    
    @property
    def ltn(self) -> ShNode:
        n = self.node(H0N.ltn)
        if n is None:
            raise Exception(f"{H0N.ltn} is known to exist")
        return n
    
    @property
    def pico_cycler(self) -> ShNode:
        n = self.node(H0N.pico_cycler)
        if n is None:
            raise Exception(f"{H0N.pico_cycler} is known to exist")
        return n

    @property
    def dist_010v(self) -> ShNode:
        n = self.node(H0N.dist_010v)
        if n is None:
            raise Exception(f"{H0N.dist_010v} is known to exist")
        return n

    @property
    def store_010v(self) -> ShNode:
        n = self.node(H0N.store_010v)
        if n is None:
            raise Exception(f"{H0N.store_010v} is known to exist")
        return n

    @property
    def primary_010v(self) -> ShNode:
        n = self.node(H0N.primary_010v)
        if n is None:
            raise Exception(f"{H0N.primary_010v} is known to exist")
        return n

    ################################
    # Relays
    ################################
    #
    # One property per relay CONCEPT — the thing control code commands — so a
    # caller asks the layout for `iso_valve` and never learns which plant it is
    # standing in. A concept both families name the same way reads the shared
    # name class and does not branch at all; only the genuinely divergent ones
    # do. A concept a family's plant lacks raises rather than returning None:
    # control code reaching for an absent actuator is a bug, not a branch.

    @property
    def is_nolan(self) -> bool:
        return self.layout_type_name == NOLAN_LAYOUT_TYPE_NAME

    def required_node(self, name: str) -> ShNode:
        """A node the layout word's axioms force to exist. A miss means the
        contract was bypassed."""
        node = self.node(name)
        if node is None:
            contract = (
                f"a {self.layout_type_name} axiom"
                if self.layout_type_name
                else "the layout contract"
            )
            raise DcError(
                f"required node {name} absent from layout ({contract} was bypassed)"
            )
        return node

    def _family_only(self, concept: str, layout_type_name: str) -> ShNode | None:
        """Refuse a relay concept the other family's plant does not have."""
        if self.layout_type_name != layout_type_name:
            raise DcError(
                f"a {self.layout_type_name} plant has no {concept} relay"
            )
        return None

    # --- shared, same name in both families ---

    @property
    def vdc_relay(self) -> ShNode:
        """The 5V DC bus relay the pico cycler power-cycles. Both families name
        it the same thing: the gw108 carries it on a native GPIO and the Krida
        board on position 1, but where the wire lands is the component's
        business, not the node's name."""
        return self.required_node(HSNN.vdc_relay)

    @property
    def hp_scada_ops_relay(self) -> ShNode:
        """Calls the heat pump on and off."""
        return self.required_node(HSNN.hp_scada_ops_relay)

    # --- shared concept, different node per family ---

    @property
    def iso_valve(self) -> ShNode:
        """The relay throwing the store's isolation valve.

        On Nolan this relay does that and only that. On House0 it is the
        charge/discharge relay: one relay throwing both the ISO valve and the
        charge/discharge valve, so opening the ISO valve there also puts the
        plant in the discharge position. Command it through
        `store_charge_discharge_relay` when the charge/discharge sense is what
        you mean.
        """
        if self.is_nolan:
            return self.required_node(NolanNodeNames.iso_valve_relay)
        return self.required_node(House0NodeNames.store_charge_discharge_relay)

    @property
    def store_charge_discharge_relay(self) -> ShNode:
        """Selects charging vs discharging the store.

        House0 does this with a two-way valve on the same relay as the ISO
        valve (see `iso_valve`); Nolan with a separate open/close discharge
        valve, so the two are distinct nodes there.
        """
        if self.is_nolan:
            return self.required_node(NolanNodeNames.discharge_valve_relay)
        return self.required_node(House0NodeNames.store_charge_discharge_relay)

    @property
    def store_pump_relay(self) -> ShNode:
        """Turns the store pump on and off."""
        if self.is_nolan:
            return self.required_node(NolanNodeNames.store_pump_relay)
        return self.required_node(House0NodeNames.store_pump_failsafe)

    # --- House0 plant only ---

    @property
    def tstat_common_relay(self) -> ShNode:
        self._family_only("tstat common", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.tstat_common_relay)

    @property
    def hp_failsafe_relay(self) -> ShNode:
        """Hands heat-pump control to the scada or back to the tank aquastat."""
        self._family_only("hp failsafe", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.hp_failsafe_relay)

    @property
    def thermistor_common_relay(self) -> ShNode:
        self._family_only("thermistor common", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.thermistor_common_relay)

    @property
    def aquastat_control_relay(self) -> ShNode:
        """Hands the aquastat to the scada or back to the oil boiler."""
        self._family_only("aquastat ctrl", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.aquastat_ctrl_relay)

    @property
    def boiler_scada_ops(self) -> ShNode:
        """Calls the oil boiler. Nolan has no boiler."""
        self._family_only("boiler scada ops", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.boiler_scada_ops)

    @property
    def primary_pump_scada_ops(self) -> ShNode:
        """Nolan does not control its primary pump."""
        self._family_only("primary pump scada ops", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.primary_pump_scada_ops)

    @property
    def primary_pump_failsafe(self) -> ShNode:
        """Hands the primary pump to the scada or back to the heat pump."""
        self._family_only("primary pump failsafe", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.primary_pump_failsafe)

    @property
    def hp_loop_on_off(self) -> ShNode:
        """Drives the Siegenthaler loop valve (with `hp_loop_keep_send`).
        Nolan has no Siegenthaler loop."""
        self._family_only("hp loop on/off", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.hp_loop_on_off)

    @property
    def hp_loop_keep_send(self) -> ShNode:
        """Sets which way `hp_loop_on_off` moves the Siegenthaler valve."""
        self._family_only("hp loop keep/send", HOUSE0_LAYOUT_TYPE_NAME)
        return self.required_node(House0NodeNames.hp_loop_keep_send)

    # --- Nolan plant only ---

    @property
    def secondary_pump_relay(self) -> ShNode:
        """Turns the secondary (heat-exchanger side) pump on and off. House0
        has no heat exchanger, so no such pump."""
        self._family_only("secondary pump", NOLAN_LAYOUT_TYPE_NAME)
        return self.required_node(NolanNodeNames.secondary_pump_relay)

    @property
    def store_top_elt_relay(self) -> ShNode:
        """Switches the store tank's top electric element."""
        self._family_only("store top element", NOLAN_LAYOUT_TYPE_NAME)
        return self.required_node(NolanNodeNames.store_top_elt_relay)

    @property
    def store_bottom_elt_relay(self) -> ShNode:
        """Switches the store tank's bottom electric element."""
        self._family_only("store bottom element", NOLAN_LAYOUT_TYPE_NAME)
        return self.required_node(NolanNodeNames.store_bottom_elt_relay)

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

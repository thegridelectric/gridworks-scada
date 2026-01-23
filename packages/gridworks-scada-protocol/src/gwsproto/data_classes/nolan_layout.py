import json
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from gwsproto.errors import DcError
from gwsproto.enums import ActorClass
from gwsproto.data_classes.components import Component
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.components.web_server_component import WebServerComponent

from gwsproto.data_classes.house_0_names import ScadaWeb

from gwsproto.data_classes.nolan_names import NhN, NhCN
from gwsproto.enums import FlowManifoldVariant

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.decoders import (
    CacDecoder,
    ComponentDecoder,
)
from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.named_types import TankTempCalibrationMap
from gwsproto.data_classes.hardware_layout import (
    HardwareLayout,
    LoadArgs,
    LoadError,
)

class LayoutBucket(str, Enum): 
    ADS111X = "Ads111xBased"
    ELECTRIC_METER = "ElectricMeter"
    OTHER = "Other"

    @property
    def device_type_list_name(self) -> str:
        """e.g. OtherCacs"""
        return f"{self.value}Cacs"

    @property
    def component_list_name(self) -> str:
        """e.g. OtherComponents"""
        return f"{self.value}Components"


class NolanLoadArgs(LoadArgs):
    flow_manifold_variant: FlowManifoldVariant


class NolanLayout(HardwareLayout):
    zone_list: List[str]
    critical_zone_list: List[str]
    zone_kwh_per_deg_f_list: List[float]
    total_store_tanks: int

    def __init__(  # noqa: PLR0913
        self,
        layout: dict[Any, Any],
        *,
        cacs: dict[str, ComponentAttributeClassGt],  # by id
        components: dict[str, Component],  # by id
        nodes: dict[str, ShNode],  # by name
        data_channels: dict[str, DataChannel],  # by name
        derived_channels: dict[str, DerivedChannel],
        flow_manifold_variant: FlowManifoldVariant = FlowManifoldVariant.House0,
    ) -> None:
        super().__init__(
            layout=layout,
            cacs=cacs,
            components=components,
            nodes=nodes,
            data_channels=data_channels,
            derived_channels=derived_channels,
        )
        self.derived_channels = self.load_derived_channels(layout, self.nodes)
        self.flow_manifold_variant = flow_manifold_variant

        # Bolted on right now
        required_keys = ["ZoneList", "TotalStoreTanks"]
        for key in required_keys:
            if key not in layout:
                raise DcError(f"House0 requires {key}!")


        self.zone_list = layout["ZoneList"]
        self.critical_zone_list = layout["CriticalZoneList"]
        self.zone_kwh_per_deg_f_list = layout["ZoneKwhPerDegFList"]
        self.total_store_tanks = layout["TotalStoreTanks"]

        self.channels = NhCN(self.total_store_tanks, self.zone_list)
        if not isinstance(self.total_store_tanks, int):
            raise TypeError("TotalStoreTanks must be an integer")
        if not 1 <= self.total_store_tanks <= 6:
            raise ValueError("Must have between 1 and 6 store tanks")
        if not isinstance(self.zone_list, List):
            raise TypeError("ZoneList must be a list")
        if not 1 <= len(self.zone_list) <= 6:
            raise ValueError("Must have between 1 and 6 store zones")
        if not isinstance(self.critical_zone_list, List):
            raise TypeError("CriticalZoneList must be a list")
        if not len(self.critical_zone_list) <= len(self.zone_list):
            raise ValueError("CriticalZoneList must be a subset of ZoneList")
        for zone in self.critical_zone_list:
            if zone not in self.zone_list:
                raise ValueError(f"{zone} is in CriticalZoneList but not in ZoneList")
        if not isinstance(self.zone_kwh_per_deg_f_list, List):
            raise TypeError("ZoneKwhPerDegFList must be a list")
        if not len(self.zone_kwh_per_deg_f_list) == len(self.zone_list):
            raise ValueError("ZoneKwhPerDegFList must have the same number of elements as ZoneList")
        self.names = NhN(self.total_store_tanks, self.zone_list)

        web_servers = {
            ws.web_server_gt.Name
            for ws in self.get_components_by_type(WebServerComponent)
        }

        if ScadaWeb.DEFAULT_SERVER_NAME not in web_servers:
            raise ValueError(
                f"NolanLayout requires a WebServerComponent named "
                f"'{ScadaWeb.DEFAULT_SERVER_NAME}'"
            )

        if len(self.tank_temp_calibration_map.Tank) != self.total_store_tanks:
            raise DcError(f"Tank Temp Calibration Map has {len(self.tank_temp_calibration_map.Tank)} tanks"
                          f" but system has {self.total_store_tanks}")


    @property
    def unreported_channels(self) -> set[str]:
        """
        Channels that must exist in the layout but are NOT reported upstream.
        """
        # Example: exclude all device-level temperature channels
        # (kept locally for diagnostics and derived generation)
        # unreported: set[str] = set()

        # # Buffer device channels
        # unreported |= self.NhCN.buffer.device

        # # Tank device channels
        # for tank in self.NhCN.tank.values():
        #     unreported |= tank.device

        # return unreported

        return set()

    @property
    def tank_device_temp_channels(self) -> set[str]:
        channels = set(self.channels.buffer.devices)
        for tank in self.channels.tank.values():
            channels |= tank.devices
        return channels

    @property
    def tank_temp_calibration_map(self) -> TankTempCalibrationMap:
        node = self.nodes.get(NhN.derived_generator)
        if node is None:
            raise ValueError(
                "NolanLayout invariant violated: "
                "derived-generator node is missing"
            )

        raw = getattr(node, "TankTempCalibrationMap", None)
        if raw is None:
            raise ValueError(
                "NolanLayout invariant violated: "
                "derived-generator node missing TankTempCalibrationMap"
            )

        try:
            return TankTempCalibrationMap(**raw)
        except Exception as e:
            raise ValueError(
                "Invalid TankTempCalibrationMap on derived-generator node"
            ) from e

    @classmethod
    def validate_nolan(  # noqa: C901
        cls,
        load_args: NolanLoadArgs,
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
            NhN.ltn,
            NhN.primary_scada,
            NhN.leaf_ally,
            NhN.local_control,
            NhN.derived_generator,
        ]

        # Add pico_cycler if there are any pico-based actors
        pico_actor_classes = [ActorClass.ApiFlowModule, ActorClass.ApiTankModule, ActorClass.ApiBtuMeter]
        has_pico_actors = any(
            node.actor_class in pico_actor_classes
            for node in nodes.values()
        )
        if has_pico_actors:
            essential_nodes.append(NhN.pico_cycler)
            essential_nodes.append(NhN.vdc_relay)  # Also needed for pico cycling

        # Check for missing essential nodes
        missing_nodes = []
        for node_name in essential_nodes:
            if node_name not in nodes:
                missing_nodes.append(node_name)


        if missing_nodes:
            error_msg = f"Missing essential nodes in layout: {', '.join(missing_nodes)}"
            if has_pico_actors and NhN.pico_cycler in missing_nodes:
                error_msg += "\nNote: pico_cycler is required because layout contains pico-based actors"

            if raise_errors:
                raise DcError(error_msg)
            if errors is not None:
                errors_caught.append(LoadError("NolanLayout", {"missing_nodes": missing_nodes}, DcError(error_msg)))
                
        flow_manifold_variant = load_args["flow_manifold_variant"]

        # Can't use the siegenthaler loop in the code if it isn't in the plumbing
        if flow_manifold_variant != FlowManifoldVariant.NolanHouse:
            raise DcError("Must be NolanHouse flow manifold variant!")


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
    ) -> "NolanLayout":
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
    ) -> "NolanLayout":
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
        derived_channels = cls.load_derived_channels(
            layout=layout,
            nodes=nodes,
            raise_errors=raise_errors,
            errors=errors,
        )
        load_args: NolanLoadArgs = {
            "cacs": cacs,
            "components": components,
            "nodes": nodes,
            "data_channels": data_channels,
            "derived_channels": derived_channels,
            "flow_manifold_variant": FlowManifoldVariant(layout.get("FlowManifoldVariant", "House0")),
        }
        cls.resolve_links(
            load_args["nodes"],
            load_args["components"],
            raise_errors=raise_errors,
            errors=errors,
        )
        cls.validate_layout(load_args, raise_errors=raise_errors, errors=errors)
        cls.validate_nolan(load_args, raise_errors=raise_errors, errors=errors)
        return NolanLayout(layout, **load_args)

    @property
    def required_topology_nodes(self) -> set[str]:
        node_names =  (
                {
                NhN.heat_pump,
                NhN.buffer_top_elt,
                NhN.buffer_bottom_elt,
                NhN.store_top_elt,
                NhN.store_bottom_elt,
                NhN.dist_pump,
                
                NhN.store_pump,
                NhN.dist_unmixed_source,
                NhN.dist_unmixed_return,
                NhN.store_hot_pipe,
                NhN.store_cold_pipe,
                NhN.dist_flow,
                NhN.store_flow,

                NhN.vdc_relay,
            } | NhN.buffer.depths | {
                depth
                for i in self.names.tank
                for depth in self.names.tank[i].depths
            } | {
            self.names.zone[z].whitewire
            for z in self.names.zone
            } | {
                self.names.zone[z].zone
                for z in self.names.zone
            }
        )
        return node_names

    @property
    def required_system_actor_nodes(self) -> set[str]:
        return {
            NhN.primary_scada,
            NhN.primary_power_meter,
            NhN.derived_generator,
            NhN.secondary_scada,
            NhN.ltn,
            NhN.leaf_ally,
            NhN.local_control,
            NhN.local_control_normal,
            NhN.local_control_backup,
            NhN.local_control_scada_blind,
            NhN.admin,
            NhN.auto,
            NhN.pico_cycler,
            NhN.hp_boss
        }

    @property
    def optional_channels(self) -> set[str]:
        channels = {
            NhCN.oat,
        }

        return channels

    @property
    def primary_scada(self) -> ShNode:
        n = self.node(NhN.primary_scada)
        if n is None:
            raise Exception(f"{NhN.primary_scada} is known to exist")
        return n

    @property
    def derived_generator(self) -> ShNode:
        n = self.node(NhN.derived_generator)
        if n is None:
            raise Exception(f"{NhN.derived_generator} is known to exist")
        return n
    
    @property
    def local_control(self) -> ShNode:
        n = self.node(NhN.local_control)
        if n is None:
            raise Exception(f"{NhN.local_control} is known to exist")
        return n
    
    @property
    def auto_node(self) -> ShNode:
        n = self.node(NhN.auto)
        if n is None:
            raise Exception(f"{NhN.auto} is known to exist")
        return n

    @property
    def hp_boss(self) -> ShNode:
        n = self.node(NhN.hp_boss)
        if n is None:
            raise Exception(f"{NhN.hp_boss} is known to exist")
        return n
    
    @property
    def leaf_ally(self) -> ShNode:
        n = self.node(NhN.leaf_ally)
        if n is None:
            raise Exception(f"{NhN.leaf_ally} is known to exist")
        return n
    
    @property
    def ltn(self) -> ShNode:
        n = self.node(NhN.ltn)
        if n is None:
            raise Exception(f"{NhN.ltn} is known to exist")
        return n
    
    @property
    def pico_cycler(self) -> ShNode:
        n = self.node(NhN.pico_cycler)
        if n is None:
            raise Exception(f"{NhN.pico_cycler} is known to exist")
        return n

    @property
    def vdc_relay(self) -> ShNode:
        n = self.node(NhN.vdc_relay)
        if n is None:
            raise Exception(f"{NhN.vdc_relay} is known to exist")
        return n

    def scada2_gnode_name(self) -> str:
        return f"{self.scada_g_node_alias}.{NhN.secondary_scada}"

def deserialize_nolan_load_args(data: dict) -> NolanLoadArgs:
    valid_keys = set(NolanLoadArgs.__annotations__.keys())

    # Validate the FlowManifoldVariant
    data["FlowManifoldVariant"] = FlowManifoldVariant(data.get("FlowManifoldVariant", "House0"))
    # TypedDict expects a regular dictionary, so we just pass it in
    return NolanLoadArgs(**data)


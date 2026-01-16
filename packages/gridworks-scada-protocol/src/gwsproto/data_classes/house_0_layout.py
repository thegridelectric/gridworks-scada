import json
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from gwsproto.errors import DcError
from gwsproto.enums import ActorClass
from gwsproto.data_classes.components import Component
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.components.web_server_component import WebServerComponent


from gwsproto.data_classes.house_0_names import H0CN, H0N, ScadaWeb
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

class House0LoadArgs(LoadArgs):
    flow_manifold_variant: FlowManifoldVariant
    use_sieg_loop: bool

class House0Layout(HardwareLayout):
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
        use_sieg_loop: bool = False,
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
        self.use_sieg_loop = use_sieg_loop

        # Bolted on right now
        required_keys = ["ZoneList", "TotalStoreTanks"]
        for key in required_keys:
            if key not in layout:
                raise DcError(f"House0 requires {key}!")


        self.zone_list = layout["ZoneList"]
        self.critical_zone_list = layout["CriticalZoneList"]
        self.zone_kwh_per_deg_f_list = layout["ZoneKwhPerDegFList"]
        self.total_store_tanks = layout["TotalStoreTanks"]

        self.h0cn = H0CN(self.total_store_tanks, self.zone_list)
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
        self.h0n = H0N(self.total_store_tanks, self.zone_list)

        web_servers = {
            ws.web_server_gt.Name
            for ws in self.get_components_by_type(WebServerComponent)
        }

        if ScadaWeb.DEFAULT_SERVER_NAME not in web_servers:
            raise ValueError(
                f"House0Layout requires a WebServerComponent named "
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

    @property
    def tank_temp_calibration_map(self) -> TankTempCalibrationMap:
        node = self.nodes.get(H0N.derived_generator)
        if node is None:
            raise ValueError(
                "House0Layout invariant violated: "
                "derived-generator node is missing"
            )

        raw = getattr(node, "TankTempCalibrationMap", None)
        if raw is None:
            raise ValueError(
                "House0Layout invariant violated: "
                "derived-generator node missing TankTempCalibrationMap"
            )

        try:
            return TankTempCalibrationMap(**raw)
        except Exception as e:
            raise ValueError(
                "Invalid TankTempCalibrationMap on derived-generator node"
            ) from e

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
            H0N.relay_multiplexer,
            H0N.vdc_relay,
            H0N.tstat_common_relay,
            H0N.store_charge_discharge_relay,
            H0N.thermistor_common_relay,
            H0N.aquastat_ctrl_relay,
            H0N.store_pump_failsafe,
            H0N.primary_pump_scada_ops,
            H0N.primary_pump_failsafe
        ]


        # Add pico_cycler if there are any pico-based actors
        pico_actor_classes = [ActorClass.ApiFlowModule, ActorClass.ApiTankModule, ActorClass.ApiBtuMeter]
        has_pico_actors = any(
            node.actor_class in pico_actor_classes
            for node in nodes.values()
        )
        if has_pico_actors:
            essential_nodes.append(H0N.pico_cycler)
            essential_nodes.append(H0N.vdc_relay)  # Also needed for pico cycling

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
                errors_caught.append(LoadError("House0Layout", {"missing_nodes": missing_nodes}, DcError(error_msg)))
                
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
        derived_channels = cls.load_derived_channels(
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
            "derived_channels": derived_channels,
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
    def required_topology_nodes(self) -> set[str]:
        node_names =  (
                {
                H0N.hp_odu,
                H0N.hp_idu,
        
                H0N.dist_pump,
                H0N.primary_pump,
                H0N.store_pump,

                H0N.dist_swt,
                H0N.dist_rwt,
                H0N.hp_lwt,
                H0N.hp_ewt,
                H0N.store_hot_pipe,
                H0N.store_cold_pipe,
                H0N.buffer_hot_pipe,
                # NOT H0N.buffer_cold_pipe - no good place for it

                H0N.dist_flow,
                H0N.primary_flow,
                H0N.store_flow,

                H0N.vdc_relay,
                H0N.tstat_common_relay,
                H0N.store_charge_discharge_relay,
                H0N.hp_failsafe_relay,
                H0N.hp_scada_ops_relay,
                H0N.thermistor_common_relay,
                H0N.aquastat_ctrl_relay,
                H0N.store_pump_failsafe,
                H0N.primary_pump_scada_ops,
                H0N.primary_pump_failsafe,

                H0N.dist_010v,
                H0N.primary_010v,
                H0N.store_010v,
            } | H0N.buffer.depths | {
                depth
                for i in self.h0n.tank
                for depth in self.h0n.tank[i].depths
            } | {
            self.h0n.zone[z].whitewire
            for z in self.h0n.zone
            } | {
                self.h0n.zone[z].zone
                for z in self.h0n.zone
            }
        )
        return node_names

    @property
    def required_system_actor_nodes(self) -> set[str]:
        return {
            H0N.primary_scada,
            H0N.primary_power_meter,
            H0N.derived_generator,
            H0N.secondary_scada,
            H0N.ltn,
            H0N.leaf_ally,
            H0N.local_control,
            H0N.local_control_normal,
            H0N.local_control_backup,
            H0N.local_control_scada_blind,
            H0N.admin,
            H0N.auto,
            H0N.pico_cycler,
            H0N.hp_boss
        }

    @property
    def optional_channels(self) -> set[str]:
        channels = {
            H0CN.buffer_cold_pipe,
            H0CN.oat,
            H0CN.sieg_cold,
            H0CN.sieg_flow,
        }
        # add store channels and thermostat channels
        return channels

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
    def vdc_relay(self) -> ShNode:
        n = self.node(H0N.vdc_relay)
        if n is None:
            raise Exception(f"{H0N.vdc_relay} is known to exist")
        return n

    @property
    def tstat_common_relay(self) -> ShNode:
        n = self.node(H0N.tstat_common_relay)
        if n is None:
            raise Exception(f"{H0N.tstat_common_relay} is known to exist")
        return n

    @property
    def charge_discharge_relay(self) -> ShNode:
        n = self.node(H0N.store_charge_discharge_relay)
        if n is None:
            raise Exception(f"{H0N.store_charge_discharge_relay} is known to exist")
        return n

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


import json
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional
from gwsproto.errors import DcError
from gwsproto import type_name_literal
from gwsproto.enums import ActorClass
from gwsproto.data_classes.components import Component
from gwsproto.data_classes.data_channel import DataChannel
from gwsproto.data_classes.components.web_server_component import WebServerComponent
from gwsproto.names.house0.node_names import House0NodeNames
from gwsproto.names.nolan.node_names import NolanNodeNames


from gwsproto.data_classes.house_0_names import H0CN, H0N, ScadaWeb
from gwsproto.enums import FlowManifoldVariant
from gwsproto.named_types.hvac_zone import HvacZone
from gwsproto.named_types.gw_hydronic import GwHydronic

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.decoders import (
    ComponentDecoder,
    DeviceTypeDecoder,
)
from gwsproto.data_classes.derived_channel import DerivedChannel
from gwsproto.named_types import (
    RequiredEnergyLayered,
    UsableEnergyLayered,
)
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

class House0Layout(HardwareLayout):

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
        super().__init__(
            layout=layout,
            device_types=device_types,
            components=components,
            nodes=nodes,
            data_channels=data_channels,
            derived_channels=derived_channels,
        )
        self.derived_channels = self.load_derived_channels(layout, self.nodes)

        # ---- Hydronic block (the gw.hydronic type lives on the dataclass) ----
        # Accept the typed nested "Hydronic" if present; else build it from the legacy
        # flat top-level keys (transitional, while layout_gen + fixtures migrate).
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
                f"House0Layout requires a WebServerComponent named "
                f"'{ScadaWeb.DEFAULT_SERVER_NAME}'"
            )

        self.validate_tank_temp_calibration_consistency()
        self.validate_house0_system_models()

    @property
    def vdc_relay_name(self) -> str:
        # Strategy now lives on the typed Hydronic block; fall back to the legacy
        # top-level key for pre-nesting layouts.
        strategy = self.hydronic.Strategy or self.layout.get(
            "Strategy", HouseStrategy.House0.value
        )
        if strategy == HouseStrategy.Nolan.value:
            return NolanNodeNames.vdc_relay
        return House0NodeNames.vdc_relay

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
            type_name_literal(UsableEnergyLayered),
            type_name_literal(RequiredEnergyLayered),
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

    @staticmethod
    def _build_hydronic(
        layout: dict,
        derived_channels: dict,
        flow_manifold_variant: FlowManifoldVariant,
        use_sieg_loop: bool,
    ) -> GwHydronic:
        """The typed gw.hydronic for this layout: read the nested 'Hydronic'
        block if present, else build it from the legacy flat top-level keys
        (transitional, while layout_gen + fixtures migrate to the nested block)."""
        h = layout.get("Hydronic")
        if isinstance(h, dict) and "Zones" in h:
            return GwHydronic.model_validate(h)
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
        return GwHydronic(
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
    ) -> "House0Layout":
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
    ) -> "House0Layout":
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
        return House0Layout(layout, **load_args)

    @property
    def required_topology_nodes(self) -> set[str]:
        """DESIGN BRAINSTORM — NOT USED YET. A first-guess spec of the topology
        nodes the five production homes need; enforced nowhere. Written in old
        `H0N` terms and already known too strict (e.g. it lists `H0N.hp_idu`, but
        maple now runs `hp_odu`-only and is still House0). To be reworked into real
        per-layout axioms in hardware-layout-pass-2, after `H0N` is dropped."""
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
        """DESIGN BRAINSTORM — NOT USED YET. A first-guess spec of the system actor
        nodes the production homes need; enforced nowhere. Written in old `H0N`
        terms; to be reworked into real per-layout axioms in
        hardware-layout-pass-2, after `H0N` is dropped."""
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

    @property
    def vdc_relay(self) -> ShNode:
        name = self.vdc_relay_name
        n = self.node(name)
        if n is None:
            if name == NolanNodeNames.vdc_relay:
                raise Exception(
                    f"VDC relay node {name!r} missing from hardware layout "
                    "(expected for Strategy Nolan / Gw108 GPIO). Regenerate layout with "
                    "add_nolan_relays(), or if this install uses Krida multiplexed relays "
                    f"instead, set Strategy to House0 so the relay node resolves to "
                    f"{House0NodeNames.vdc_relay!r}."
                )
            raise Exception(f"VDC relay node {name!r} missing from hardware layout.")
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

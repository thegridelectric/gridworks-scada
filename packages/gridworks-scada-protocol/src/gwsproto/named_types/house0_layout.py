from typing import Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import ActorClass

from gwsproto.named_types.ads111x_based_component_gt import Ads111xBasedComponentGt
from gwsproto.named_types.ads111x_based_device_type_gt import Ads111xBasedDeviceTypeGt
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.device_component_gt import DeviceComponentGt
from gwsproto.named_types.dfr_component_gt import DfrComponentGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.named_types.g_node_gt import GNodeGt
from gwsproto.named_types.hydronic import Hydronic
from gwsproto.named_types.hp_device_type_gt import HpDeviceTypeGt
from gwsproto.named_types.hubitat_component_gt import HubitatComponentGt
from gwsproto.named_types.hubitat_poller_component_gt import HubitatPollerComponentGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from gwsproto.named_types.pico_flow_module_component_gt import PicoFlowModuleComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.sim_dac_writer_component_gt import SimDacWriterComponentGt
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.gpio_relay_component_gt import GpioRelayComponentGt
from gwsproto.named_types.gpio_sensor_component_gt import GpioSensorComponentGt
from gwsproto.named_types.i2c_dac_writer_component_gt import I2cDacWriterComponentGt
from gwsproto.named_types.i2c_relay_component_gt import I2cRelayComponentGt
from gwsproto.named_types.i2c_thermistor_reader_component_gt import (
    I2cThermistorReaderComponentGt,
)
from gwsproto.named_types.scada_board_component_gt import ScadaBoardComponentGt
from gwsproto.named_types.sim_relay_component_gt import SimRelayComponentGt
from gwsproto.named_types.sim_sensor_component_gt import SimSensorComponentGt
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType

# The component types a House0 (fleet) layout may contain (mirrors the sema oneOf).
House0Component = (
    ElectricMeterComponentGt
    | DeviceComponentGt
    | Ads111xBasedComponentGt
    | GpioRelayComponentGt
    | GpioSensorComponentGt
    | I2cDacWriterComponentGt
    | I2cMultichannelDtRelayComponentGt
    | I2cRelayComponentGt
    | I2cThermistorReaderComponentGt
    | DfrComponentGt
    | PicoBtuMeterComponentGt
    | PicoFlowModuleComponentGt
    | PicoTankModuleComponentGt
    | ScadaBoardComponentGt
    | SimDacWriterComponentGt
    | SimPicoTankModuleComponentGt
    | SimRelayComponentGt
    | SimSensorComponentGt
    | HubitatComponentGt
    | HubitatPollerComponentGt
    | WebServerComponentGt
)

# The specialized device-type records a House0 layout may carry (mirrors the sema oneOf).
House0DeviceType = (
    Ads111xBasedDeviceTypeGt
    | ElectricMeterDeviceTypeGt
    | ScadaDeviceTypeGt
    | HpDeviceTypeGt
)


class House0Layout(GwsprotoSemaType):
    """
    Sema: https://schemas.electricity.works/types/gw.house0.layout/000
    """

    GNodes: list[GNodeGt]
    ShNodes: list[SpaceheatNodeGt]
    DataChannels: list[DataChannelGt]
    DerivedChannels: list[DerivedChannelGt]
    Components: list[House0Component]
    DeviceTypes: list[House0DeviceType]
    Hydronic: Hydronic
    TypeName: Literal["gw.house0.layout"] = "gw.house0.layout"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: GlobalIdUniqueness
        ShNode.ShNodeId, Component.ComponentId, DataChannel.Id, DerivedChannel.Id
        and GNode.GNodeId SHALL each be globally unique; no id value SHALL appear
        in more than one of these sets.
        """
        ids: list[str] = []
        ids += [n.ShNodeId for n in (self.ShNodes or [])]
        ids += [c.ComponentId for c in (self.Components or [])]
        ids += [d.Id for d in (self.DataChannels or [])]
        ids += [d.Id for d in (self.DerivedChannels or [])]
        ids += [g.GNodeId for g in (self.GNodes or [])]
        seen: set[str] = set()
        dupes: set[str] = set()
        for i in ids:
            if i in seen:
                dupes.add(i)
            seen.add(i)
        if dupes:
            raise ValueError(
                f"Axiom 1 (GlobalIdUniqueness) failed: duplicate ids {sorted(dupes)}"
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: CoreShNodesExistenceAndActorClass
        ShNodes SHALL contain a node with each of the following Name /
        ActorClass pairs, and no additional ShNode with any of these Names
        SHALL exist:
          "s"                 → ActorClass "PrimaryScada"
          "s2"                → ActorClass "SecondaryScada"
          "power-meter"       → ActorClass "PowerMeter"
          "ltn"               → ActorClass "NoActor"
          "admin"             → ActorClass "NoActor"
          "auto"              → ActorClass "NoActor"
          "la"                → ActorClass "LeafAlly"
          "lc"                → ActorClass "LocalControl"
          "derived-generator" → ActorClass "DerivedGenerator"
        The effective handle (Handle if present, otherwise Name) of "admin"
        SHALL be "admin" and of "auto" SHALL be "auto".
        """
        if not self.ShNodes:
            return self
        pairs = {
            "s": ActorClass.PrimaryScada,
            "s2": ActorClass.SecondaryScada,
            "power-meter": ActorClass.PowerMeter,
            "ltn": ActorClass.NoActor,
            "admin": ActorClass.NoActor,
            "auto": ActorClass.NoActor,
            "la": ActorClass.LeafAlly,
            "lc": ActorClass.LocalControl,
            "derived-generator": ActorClass.DerivedGenerator,
        }
        nodes_by_name: dict[str, list] = {}
        for n in self.ShNodes:
            nodes_by_name.setdefault(n.Name, []).append(n)
        for name, actor_class in pairs.items():
            matches = nodes_by_name.get(name, [])
            if len(matches) != 1 or matches[0].ActorClass != actor_class:
                raise ValueError(
                    f"Axiom 2 (CoreShNodesExistenceAndActorClass) failed: expected exactly one "
                    f"ShNode {name!r} with ActorClass {actor_class}."
                )
        for name, handle in (("admin", "admin"), ("auto", "auto")):
            node = nodes_by_name[name][0]
            effective = node.Handle if node.Handle is not None else node.Name
            if effective != handle:
                raise ValueError(
                    f"Axiom 2 (CoreShNodesExistenceAndActorClass) failed: {name!r} effective "
                    f"handle is {effective!r}, expected {handle!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> Self:
        """
        Axiom 3: CommandNodesExistenceAndActorClass
        ShNodes SHALL contain a node with each of the following Name /
        ActorClass pairs, and no additional ShNode with any of these Names
        SHALL exist:
          "n"           → ActorClass "NoActor"
          "backup"      → ActorClass "NoActor"
          "scada-blind" → ActorClass "NoActor"
          "pico-cycler" → ActorClass "PicoCycler"
          "hp-boss"     → ActorClass "HpBoss"
          "sieg-loop"   → ActorClass "SiegLoop"
        The effective handle of "n" SHALL be "auto.lc.n". (A gw.house0.layout
        plant has a siegenthaler loop; whether the loop is USED is
        operational, so sieg-loop and hp-boss are unconditional command
        nodes, dormant when unused.)
        """
        if not self.ShNodes:
            return self
        pairs = {
            "n": ActorClass.NoActor,
            "backup": ActorClass.NoActor,
            "scada-blind": ActorClass.NoActor,
            "pico-cycler": ActorClass.PicoCycler,
            "hp-boss": ActorClass.HpBoss,
            "sieg-loop": ActorClass.SiegLoop,
        }
        nodes_by_name: dict[str, list] = {}
        for n in self.ShNodes:
            nodes_by_name.setdefault(n.Name, []).append(n)
        for name, actor_class in pairs.items():
            matches = nodes_by_name.get(name, [])
            if len(matches) != 1 or matches[0].ActorClass != actor_class:
                raise ValueError(
                    f"Axiom 3 (CommandNodesExistenceAndActorClass) failed: expected exactly one "
                    f"ShNode {name!r} with ActorClass {actor_class}."
                )
        n_node = nodes_by_name["n"][0]
        effective = n_node.Handle if n_node.Handle is not None else n_node.Name
        if effective != "auto.lc.n":
            raise ValueError(
                f"Axiom 3 (CommandNodesExistenceAndActorClass) failed: 'n' effective handle is "
                f"{effective!r}, expected 'auto.lc.n'."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> Self:
        """
        Axiom 4: ZoneHeatCallChannel
        For each zone at 1-based index i in Hydronic.Zones, a DerivedChannel named
        "zone{i}-{Zone.Name}-heat-call" (lowercased) with Strategy "heat-call" SHALL exist,
        and a source DataChannel SHALL exist for that zone — either
        "zone{i}-{Zone.Name}-whitewire-pwr" (power-sourced) or "zone{i}-{Zone.Name}-opto-input"
        (opto-sourced). The choice of source is per-zone.
        """
        if self.Hydronic is None:
            return self
        derived_by_name = {d.Name: d for d in (self.DerivedChannels or [])}
        data_names = {d.Name for d in (self.DataChannels or [])}
        for i, zone in enumerate(self.Hydronic.Zones or [], start=1):
            base = f"zone{i}-{zone.Name}".lower()
            heat_call = f"{base}-heat-call"
            dc = derived_by_name.get(heat_call)
            if dc is None:
                raise ValueError(
                    f"Axiom 4 (ZoneHeatCallChannel) failed: missing DerivedChannel '{heat_call}'."
                )
            if dc.Strategy != "heat-call":
                raise ValueError(
                    f"Axiom 4 (ZoneHeatCallChannel) failed: DerivedChannel '{heat_call}' must have "
                    f"Strategy 'heat-call', got '{dc.Strategy}'."
                )
            whitewire = f"{base}-whitewire-pwr"
            opto = f"{base}-opto-input"
            if whitewire not in data_names and opto not in data_names:
                raise ValueError(
                    f"Axiom 4 (ZoneHeatCallChannel) failed: heat-call for zone {i} needs a source "
                    f"DataChannel — '{whitewire}' (power) or '{opto}' (opto)."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> Self:
        """
        Axiom 5: PrimaryFlowSourceChannelAgreement
        The "primary-flow" channel SHALL agree with Hydronic.PrimaryFlowSource. If
        PrimaryFlowSource is "Measured", a DataChannel named "primary-flow" SHALL exist
        and no DerivedChannel named "primary-flow" SHALL exist. If PrimaryFlowSource is
        "DerivedSiegSum", a DerivedChannel named "primary-flow" with Strategy "sum" SHALL
        exist and no DataChannel named "primary-flow" SHALL exist.
        """
        if self.Hydronic is None:
            return self
        source = self.Hydronic.PrimaryFlowSource
        has_data = any(d.Name == "primary-flow" for d in (self.DataChannels or []))
        derived = [d for d in (self.DerivedChannels or []) if d.Name == "primary-flow"]
        if source == "Measured":
            if not has_data:
                raise ValueError(
                    "Axiom 5 (PrimaryFlowSourceChannelAgreement) failed: Measured requires a "
                    "'primary-flow' DataChannel."
                )
            if derived:
                raise ValueError(
                    "Axiom 5 (PrimaryFlowSourceChannelAgreement) failed: Measured forbids a "
                    "'primary-flow' DerivedChannel."
                )
        elif source == "DerivedSiegSum":
            if not any(d.Strategy == "sum" for d in derived):
                raise ValueError(
                    "Axiom 5 (PrimaryFlowSourceChannelAgreement) failed: DerivedSiegSum requires "
                    "a 'primary-flow' DerivedChannel with Strategy 'sum'."
                )
            if has_data:
                raise ValueError(
                    "Axiom 5 (PrimaryFlowSourceChannelAgreement) failed: DerivedSiegSum forbids a "
                    "'primary-flow' DataChannel."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> Self:
        """
        Axiom 7: RequiredSensing
        For each required sensing name, a channel with that Name SHALL exist
        in DataChannels or in DerivedChannels (kind-agnostic).
        """
        if not self.ShNodes:
            return self
        names = {c.Name for c in (self.DataChannels or [])} | {
            c.Name for c in (self.DerivedChannels or [])
        }
        missing = sorted({"dist-flow", "store-flow"} - names)
        if missing:
            raise ValueError(
                f"Axiom 7 (RequiredSensing) failed: missing channel(s) {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_8(self) -> Self:
        """
        Axiom 8: SiegManifoldChannels
        The sieg loop's sensing and valve-observation channels SHALL exist
        (unconditional — a gw.house0.layout plant has a sieg loop).
        """
        if not self.ShNodes:
            return self
        names = {c.Name for c in (self.DataChannels or [])} | {
            c.Name for c in (self.DerivedChannels or [])
        }
        required = {
            "sieg-cold",
            "sieg-flow",
            "sieg-flow-hz",
            "hp-loop-on-off-relay",
            "hp-loop-keep-send-relay",
        }
        missing = sorted(required - names)
        if missing:
            raise ValueError(
                f"Axiom 8 (SiegManifoldChannels) failed: missing channel(s) {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> Self:
        """
        Axiom 6: TransactivePowerChannel
        Exactly one transactive-power DerivedChannel; each input resolves to
        a PowerW DataChannel whose AboutNode carries a NameplatePowerW.
        """
        if not self.ShNodes:
            return self
        transactive = [
            d for d in (self.DerivedChannels or [])
            if d.Strategy == "transactive-power"
        ]
        if len(transactive) != 1:
            raise ValueError(
                "Axiom 6 (TransactivePowerChannel) failed: expected exactly one "
                f"transactive-power DerivedChannel, found {len(transactive)}."
            )
        data_by_name = {d.Name: d for d in (self.DataChannels or [])}
        node_by_name = {n.Name: n for n in (self.ShNodes or [])}
        for name in transactive[0].InputChannelNames:
            ch = data_by_name.get(name)
            if ch is None:
                raise ValueError(
                    f"Axiom 6 (TransactivePowerChannel) failed: input '{name}' is not a DataChannel."
                )
            if ch.TelemetryName != "PowerW":
                raise ValueError(
                    f"Axiom 6 (TransactivePowerChannel) failed: input '{name}' must be PowerW, "
                    f"got '{ch.TelemetryName}'."
                )
            node = node_by_name.get(ch.AboutNodeName)
            if node is None or node.NameplatePowerW is None:
                raise ValueError(
                    f"Axiom 6 (TransactivePowerChannel) failed: about-node "
                    f"'{ch.AboutNodeName}' of input '{name}' has no NameplatePowerW."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_9(self) -> Self:
        """
        Axiom 9: SystemModelEnergyChannels
        usable-energy and required-energy DerivedChannels from the
        derived-generator with Strategy system-model, naming exactly
        gw0.usable.energy.layered and gw0.required.energy.layered.
        """
        if not self.ShNodes:
            return self
        expected_models = {
            "gw0.usable.energy.layered",
            "gw0.required.energy.layered",
        }
        derived_by_name = {d.Name: d for d in (self.DerivedChannels or [])}
        seen: set = set()
        for name in ("usable-energy", "required-energy"):
            channel = derived_by_name.get(name)
            if channel is None:
                raise ValueError(
                    "Axiom 9 (SystemModelEnergyChannels) failed: DerivedChannel "
                    f"'{name}' is absent."
                )
            if channel.CreatedByNodeName != "derived-generator":
                raise ValueError(
                    f"Axiom 9 (SystemModelEnergyChannels) failed: '{name}' must be "
                    f"created by 'derived-generator', got '{channel.CreatedByNodeName}'."
                )
            if channel.Strategy != "system-model":
                raise ValueError(
                    f"Axiom 9 (SystemModelEnergyChannels) failed: '{name}' must use "
                    f"Strategy 'system-model', got '{channel.Strategy}'."
                )
            model = (channel.Parameters or {}).get("EnergyModel") or {}
            type_name = model.get("TypeName")
            if not type_name:
                raise ValueError(
                    f"Axiom 9 (SystemModelEnergyChannels) failed: '{name}' has no "
                    "Parameters.EnergyModel.TypeName."
                )
            if type_name not in expected_models:
                raise ValueError(
                    f"Axiom 9 (SystemModelEnergyChannels) failed: '{name}' names "
                    f"unsupported EnergyModel '{type_name}'."
                )
            seen.add(type_name)
        if seen != expected_models:
            raise ValueError(
                "Axiom 9 (SystemModelEnergyChannels) failed: the two channels must "
                f"name one of each model; got {sorted(seen)}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_10(self) -> Self:
        """
        Axiom 10: RequiredActuators
        a. The eleven plant relays exist with ActorClass Relay and the three
        *-010v outputs with ActorClass ZeroTenOutputer. b. ZoneCallCircuits is
        non-empty and each circuit's relay pair names a Relay ShNode.
        """
        actor_class_by_name = {n.Name: n.ActorClass for n in self.ShNodes}

        def class_or_raise(node_name: str, expected: ActorClass, role: str) -> None:
            actor_class = actor_class_by_name.get(node_name)
            if actor_class is None:
                raise ValueError(
                    f"Axiom 10 (RequiredActuators) failed: no ShNode named "
                    f"{node_name} ({role})."
                )
            if actor_class != expected:
                raise ValueError(
                    f"Axiom 10 (RequiredActuators) failed: {node_name} ({role}) "
                    f"has ActorClass {actor_class}, not {expected.value}."
                )

        for required in (
            "vdc-relay",
            "tstat-common-relay",
            "charge-discharge-relay",
            "hp-failsafe-relay",
            "hp-scada-ops-relay",
            "aquastat-ctrl-relay",
            "store-pump-relay",
            "primary-pump-failsafe-relay",
            "primary-pump-scada-ops-relay",
            "hp-loop-on-off-relay",
            "hp-loop-keep-send-relay",
        ):
            class_or_raise(required, ActorClass.Relay, "plant relay")
        for required in ("dist-010v", "primary-010v", "store-010v"):
            class_or_raise(required, ActorClass.ZeroTenOutputer, "0-10V output")
        circuits = self.Hydronic.ZoneCallCircuits or []
        if not circuits:
            raise ValueError(
                "Axiom 10 (RequiredActuators) failed: Hydronic.ZoneCallCircuits is empty."
            )
        for circuit in circuits:
            class_or_raise(
                circuit.FailsafeRelayNode, ActorClass.Relay, "circuit failsafe relay"
            )
            class_or_raise(circuit.OpsRelayNode, ActorClass.Relay, "circuit ops relay")
        return self

    @model_validator(mode="after")
    def check_axiom_11(self) -> Self:
        """
        Axiom 11: RequiredHeatpumpEquipment
        hp-odu and hp-idu exist, each bound to a Component, each NoActor.
        """
        component_ids = {c.ComponentId for c in self.Components}
        nodes = {n.Name: n for n in self.ShNodes}
        for name in ("hp-odu", "hp-idu"):
            node = nodes.get(name)
            if node is None:
                raise ValueError(
                    f"Axiom 11 (RequiredHeatpumpEquipment) failed: no ShNode named {name!r}."
                )
            if node.ComponentId is None or node.ComponentId not in component_ids:
                raise ValueError(
                    f"Axiom 11 (RequiredHeatpumpEquipment) failed: {name!r} has no "
                    "ComponentId resolving to a Component."
                )
            if node.ActorClass != ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 11 (RequiredHeatpumpEquipment) failed: {name!r} has "
                    f"ActorClass {node.ActorClass}, expected NoActor."
                )
        return self

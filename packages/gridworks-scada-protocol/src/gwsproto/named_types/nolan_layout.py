from collections import Counter
from typing import List, Literal

from pydantic import ConfigDict, model_validator

from gwsproto.enums import ActorClass, GwZoneEmitterType, Quantity, TelemetryName
from gwsproto.named_types.ads111x_based_device_type_gt import Ads111xBasedDeviceTypeGt
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.g_node_gt import GNodeGt
from gwsproto.named_types.hp_control_box_device_type_gt import HpControlBoxDeviceTypeGt
from gwsproto.named_types.hp_device_type_gt import HpDeviceTypeGt
from gwsproto.named_types.hydronic import Hydronic
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
from gwsproto.named_types.device_component_gt import DeviceComponentGt
from gwsproto.named_types.electric_meter_component_gt import ElectricMeterComponentGt
from gwsproto.named_types.gpio_relay_component_gt import GpioRelayComponentGt
from gwsproto.named_types.gpio_sensor_component_gt import GpioSensorComponentGt
from gwsproto.named_types.i2c_dac_output_component_gt import I2cDacOutputComponentGt
from gwsproto.named_types.i2c_relay_component_gt import I2cRelayComponentGt
from gwsproto.named_types.i2c_thermistor_reader_component_gt import (
    I2cThermistorReaderComponentGt,
)
from gwsproto.named_types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.scada_board_component_gt import ScadaBoardComponentGt
from gwsproto.named_types.sim_pico_btu_meter_component_gt import (
    SimPicoBtuMeterComponentGt,
)
from gwsproto.named_types.sim_pico_flow_module_component_gt import (
    SimPicoFlowModuleComponentGt,
)
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.sim_sensor_component_gt import SimSensorComponentGt
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.board_resolution import (
    GPIO_RELAY,
    GPIO_SENSOR,
    I2C_DAC_OUTPUT,
    I2C_RELAY,
    I2C_THERMISTOR_READER,
    check_board_resolution,
)
from gwsproto.type_helpers.channel_integrity_axioms import (
    check_channel_name_uniqueness,
    check_data_channel_node_resolution,
    check_derived_channel_creator_resolution,
    check_derived_channel_inputs_acyclic,
)
from gwsproto.type_helpers.circuit_channel_axioms import (
    check_circuit_heat_call_channel,
    check_circuit_whitewire_channel_resolution,
)
from gwsproto.type_helpers.command_tree_axioms import (
    check_actuator_leaves,
    check_prefix_closed_handles,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from gwsproto.type_helpers.zone_temp_channel_resolution import (
    check_zone_temp_channel_resolution,
)

# The component types a Nolan (gw108) layout may contain (mirrors the sema draft oneOf).
NolanComponent = (
    DeviceComponentGt
    | ElectricMeterComponentGt
    | GpioSensorComponentGt
    | GpioRelayComponentGt
    | I2cDacOutputComponentGt
    | I2cRelayComponentGt
    | I2cThermistorReaderComponentGt
    | PicoBtuMeterComponentGt
    | PicoTankModuleComponentGt
    | ScadaBoardComponentGt
    | SimPicoBtuMeterComponentGt
    | SimPicoFlowModuleComponentGt
    | SimPicoTankModuleComponentGt
    | SimSensorComponentGt
    | WebServerComponentGt
)

# The specialized device-type records a Nolan layout may carry (mirrors the sema oneOf).
NolanDeviceType = (
    Ads111xBasedDeviceTypeGt
    | ElectricMeterDeviceTypeGt
    | HpControlBoxDeviceTypeGt
    | HpDeviceTypeGt
    | ScadaDeviceTypeGt
)


def exact_match_pairs(
    nodes: List[SpaceheatNodeGt],
    pairs: tuple[tuple[str, ActorClass], ...],
    axiom: str,
) -> None:
    """Exactly one ShNode per Name, carrying the paired ActorClass."""
    for name, actor_class in pairs:
        matches = [n for n in nodes if n.Name == name]
        if len(matches) != 1:
            raise ValueError(
                f"{axiom} failed: expected exactly one ShNode named {name!r}, "
                f"found {len(matches)}."
            )
        if matches[0].ActorClass != actor_class:
            raise ValueError(
                f"{axiom} failed: ShNode {name!r} has ActorClass "
                f"{matches[0].ActorClass}, expected {actor_class}."
            )


def require_effective_handles(
    nodes: List[SpaceheatNodeGt],
    expected: tuple[tuple[str, str], ...],
    axiom: str,
) -> None:
    """The effective handle (Handle if present, otherwise Name) of each named
    node equals the expected value."""
    by_name = {n.Name: n for n in nodes}
    for name, handle in expected:
        node = by_name[name]
        effective = node.Handle if node.Handle is not None else node.Name
        if effective != handle:
            raise ValueError(
                f"{axiom} failed: {name!r} effective handle is {effective!r}, "
                f"expected {handle!r}."
            )


class NolanLayout(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.nolan.layout/000"""

    GNodes: List[GNodeGt]
    ShNodes: List[SpaceheatNodeGt]
    DataChannels: List[DataChannelGt]
    DerivedChannels: List[DerivedChannelGt]
    Components: List[NolanComponent]
    DeviceTypes: List[NolanDeviceType]
    Hydronic: Hydronic
    DisabledNodeNames: List[SpaceheatName]
    DisabledChannelNames: List[SpaceheatName]
    TypeName: Literal["gw.nolan.layout"] = "gw.nolan.layout"
    Version: Literal["000"] = "000"

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def check_axiom_1(self) -> "NolanLayout":
        """Axiom 1: TransactivePowerChannel.

        DerivedChannels SHALL contain exactly one channel whose Strategy is
        "transactive-power" — the metered transactive boundary, computed by the
        power-meter actor. Each name in that channel's InputChannelNames SHALL
        resolve to an existing DataChannel with TelemetryName "PowerW", and the
        AboutNode of each such DataChannel SHALL carry a NameplatePowerW.
        """
        transactive = [
            d for d in self.DerivedChannels if d.Strategy == "transactive-power"
        ]
        if len(transactive) != 1:
            raise ValueError(
                "Axiom 1 (TransactivePowerChannel) failed: expected exactly one "
                f"transactive-power DerivedChannel, found {len(transactive)}."
            )
        data_by_name = {d.Name: d for d in self.DataChannels}
        node_by_name = {n.Name: n for n in self.ShNodes}
        for name in transactive[0].InputChannelNames:
            ch = data_by_name.get(name)
            if ch is None:
                raise ValueError(
                    "Axiom 1 (TransactivePowerChannel) failed: input "
                    f"'{name}' is not a DataChannel."
                )
            if ch.TelemetryName != "PowerW":
                raise ValueError(
                    "Axiom 1 (TransactivePowerChannel) failed: input "
                    f"'{name}' must be PowerW, got '{ch.TelemetryName}'."
                )
            node = node_by_name.get(ch.AboutNodeName)
            if node is None or node.NameplatePowerW is None:
                raise ValueError(
                    "Axiom 1 (TransactivePowerChannel) failed: about-node "
                    f"'{ch.AboutNodeName}' of input '{name}' has no NameplatePowerW."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "NolanLayout":
        """Axiom 2: BoardResolution.

        For every component in Components carrying a BoardComponentId: its
        BoardComponentId SHALL equal the ComponentId of a scada.board.component.gt in
        Components; that board component's DeviceType SHALL match the DeviceType of a
        gw1.scada.device.type.gt record in DeviceTypes; and the component's board name
        SHALL match a name in that record.
        """
        check_board_resolution(
            self.Components,
            self.DeviceTypes,
            {
                "gpio.sensor.component.gt": GPIO_SENSOR,
                "gpio.relay.component.gt": GPIO_RELAY,
                "i2c.thermistor.reader.component.gt": I2C_THERMISTOR_READER,
                "i2c.relay.component.gt": I2C_RELAY,
                "i2c.dac.output.component.gt": I2C_DAC_OUTPUT,
            },
            "Axiom 2 (BoardResolution)",
            every_board_resident=True,
        )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "NolanLayout":
        """Axiom 3: CoreShNodesExistenceAndActorClass.

        ShNodes SHALL contain a node with each of the core Name / ActorClass
        pairs (s, s2, power-meter, ltn, admin, auto, la, lc,
        derived-generator), and no additional ShNode with any of these Names
        SHALL exist. The effective handle of "admin" SHALL be "admin" and of
        "auto" SHALL be "auto".
        """
        pairs = (
            ("s", ActorClass.PrimaryScada),
            ("s2", ActorClass.SecondaryScada),
            ("power-meter", ActorClass.PowerMeter),
            ("ltn", ActorClass.NoActor),
            ("admin", ActorClass.NoActor),
            ("auto", ActorClass.NoActor),
            ("la", ActorClass.LeafAlly),
            ("lc", ActorClass.LocalControl),
            ("derived-generator", ActorClass.DerivedGenerator),
        )
        exact_match_pairs(self.ShNodes, pairs, "Axiom 3 (CoreShNodesExistenceAndActorClass)")
        require_effective_handles(
            self.ShNodes, (("admin", "admin"), ("auto", "auto")),
            "Axiom 3 (CoreShNodesExistenceAndActorClass)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "NolanLayout":
        """Axiom 4: CommandNodesExistenceAndActorClass.

        ShNodes SHALL contain "n" (NoActor), "backup" (NoActor),
        "scada-blind" (NoActor), "five-v-boss" (FiveVBoss),
        "pico-cycler" (PicoCycler) and "hp-boss" (HpBoss), with no
        additional ShNode of those Names; the effective handle of "n" SHALL
        be "auto.lc.n".
        """
        pairs = (
            ("n", ActorClass.NoActor),
            ("backup", ActorClass.NoActor),
            ("scada-blind", ActorClass.NoActor),
            ("five-v-boss", ActorClass.FiveVBoss),
            ("pico-cycler", ActorClass.PicoCycler),
            ("hp-boss", ActorClass.HpBoss),
        )
        exact_match_pairs(self.ShNodes, pairs, "Axiom 4 (CommandNodesExistenceAndActorClass)")
        require_effective_handles(
            self.ShNodes, (("n", "auto.lc.n"),),
            "Axiom 4 (CommandNodesExistenceAndActorClass)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "NolanLayout":
        """Axiom 5: RequiredActuators.

        a. ShNodes SHALL include the plant relays "vdc-relay", "iso-valve-relay",
        "secondary-pump-relay", "hp-scada-ops-relay", "charge-valve-relay",
        "store-pump-relay", "buffer-top-elt-relay", "buffer-bottom-elt-relay",
        "tank1-top-elt-relay", and "tank1-bottom-elt-relay", each with
        ActorClass "Relay".
        b. Hydronic.ZoneCallCircuits SHALL be non-empty, and each circuit's
        FailsafeRelayNode and OpsRelayNode SHALL name a ShNode in ShNodes
        with ActorClass "Relay".
        c. ShNodes SHALL include a node named "secondary-010v" with
        ActorClass "ZeroTenOutputer" and a ComponentId equal to the
        ComponentId of an i2c.dac.output.component.gt in Components.
        """
        actor_class_by_name = {n.Name: n.ActorClass for n in self.ShNodes}

        def relay_or_raise(node_name: str, role: str) -> None:
            actor_class = actor_class_by_name.get(node_name)
            if actor_class is None:
                raise ValueError(
                    f"Axiom 5 (RequiredActuators) failed: no ShNode named "
                    f"{node_name} ({role})."
                )
            if actor_class != ActorClass.Relay:
                raise ValueError(
                    f"Axiom 5 (RequiredActuators) failed: {node_name} "
                    f"({role}) has ActorClass {actor_class}, not Relay."
                )

        for required in (
            "vdc-relay",
            "iso-valve-relay",
            "secondary-pump-relay",
            "hp-scada-ops-relay",
            "charge-valve-relay",
            "store-pump-relay",
            "buffer-top-elt-relay",
            "buffer-bottom-elt-relay",
            "tank1-top-elt-relay",
            "tank1-bottom-elt-relay",
        ):
            relay_or_raise(required, "plant relay")
        circuits = self.Hydronic.ZoneCallCircuits or []
        if not circuits:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: Hydronic.ZoneCallCircuits is empty."
            )
        for circuit in circuits:
            relay_or_raise(circuit.FailsafeRelayNode, "circuit failsafe relay")
            relay_or_raise(circuit.OpsRelayNode, "circuit ops relay")
        output_node = next((n for n in self.ShNodes if n.Name == "secondary-010v"), None)
        if output_node is None:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: no ShNode named secondary-010v."
            )
        if output_node.ActorClass != ActorClass.ZeroTenOutputer:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: secondary-010v has ActorClass "
                f"{output_node.ActorClass}, not ZeroTenOutputer."
            )
        dac_output_ids = {
            c.ComponentId
            for c in self.Components
            if isinstance(c, I2cDacOutputComponentGt)
        }
        if output_node.ComponentId not in dac_output_ids:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: secondary-010v ComponentId "
                f"{output_node.ComponentId} is not an i2c.dac.output.component.gt "
                "in Components."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "NolanLayout":
        """Axiom 6: RequiredHeatpumpEquipment.

        ShNodes SHALL include nodes named "hp-odu" and "hp-ctrl-box" (a Nolan
        home is a monobloc), each with a ComponentId equal to the ComponentId
        of a Component in Components, and each with ActorClass "NoActor"
        unless it is the declared HpCommandNodeName (CommandableHeatPump).
        """
        component_ids = {c.ComponentId for c in self.Components}
        nodes = {n.Name: n for n in self.ShNodes}
        for name in ("hp-odu", "hp-ctrl-box"):
            node = nodes.get(name)
            if node is None:
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: no ShNode named {name!r}."
                )
            if node.ComponentId is None or node.ComponentId not in component_ids:
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: {name!r} has no "
                    "ComponentId resolving to a Component."
                )
            if name == self.Hydronic.HpCommandNodeName:
                continue  # ActorClass governed by CommandableHeatPump
            if node.ActorClass != ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: {name!r} has "
                    f"ActorClass {node.ActorClass}, expected NoActor."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> "NolanLayout":
        """Axiom 7: ComponentBinding.

        Every Component in Components SHALL have its ComponentId referenced by
        exactly one ShNode in ShNodes.
        """
        refs = Counter(n.ComponentId for n in self.ShNodes if n.ComponentId)
        violations = {
            c.ComponentId: refs.get(c.ComponentId, 0)
            for c in self.Components
            if refs.get(c.ComponentId, 0) != 1
        }
        if violations:
            raise ValueError(
                "Axiom 7 (ComponentBinding) failed: components not referenced by "
                f"exactly one ShNode (id: reference count) {violations}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_8(self) -> "NolanLayout":
        """Axiom 8: RequiredSensing.

        For each required sensing name: a channel with that Name SHALL exist
        in DataChannels or in DerivedChannels. (Kind-agnostic by design: a
        name may migrate from raw DataChannel to same-name DerivedChannel
        without touching this contract.)
        """
        channel_names = {c.Name for c in self.DataChannels} | {
            c.Name for c in self.DerivedChannels
        }
        missing = [
            name
            for name in (
                "hp-lwt", "hp-ewt", "dist-swt", "dist-rwt",
                "store-hot-pipe", "store-cold-pipe",
                "secondary-lwt", "secondary-ewt", "buffer-cold-pipe",
                "fancoil-swt", "fancoil-rwt", "floor-swt", "floor-rwt",
                "dist-flow", "primary-flow", "store-flow", "secondary-flow",
                "hp-odu-pwr", "hp-ctrl-box-pwr",
                "primary-pump-pwr", "store-pump-pwr", "dist-pump-pwr",
                "secondary-pump-pwr",
                "buffer-top-elt-pwr", "buffer-bottom-elt-pwr",
                "tank1-top-elt-pwr", "tank1-bottom-elt-pwr",
            )
            if name not in channel_names
        ]
        if missing:
            raise ValueError(
                f"Axiom 8 (RequiredSensing) failed: missing channels {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_9(self) -> "NolanLayout":
        """Axiom 9: SingleStoreTank.

        Hydronic.TotalStoreTanks SHALL equal 1 — the Nolan plant carries
        exactly one store tank.
        """
        if self.Hydronic.TotalStoreTanks != 1:
            raise ValueError(
                f"Axiom 9 (SingleStoreTank) failed: TotalStoreTanks is "
                f"{self.Hydronic.TotalStoreTanks}, expected 1."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_10(self) -> "NolanLayout":
        """
        Axiom 10: CommandableHeatPump.
        a. If Hydronic.HpCommandNodeName is present, it names an ShNode called
        hp-odu, hp-idu or hp-ctrl-box, bound to a Component, with ActorClass
        HpTwin, whose effective handle sits directly under hp-boss's.
        b. Every HpTwin-classed ShNode is the declared node; none when absent.
        """
        declared = self.Hydronic.HpCommandNodeName
        nodes = {n.Name: n for n in self.ShNodes}
        if declared is not None:
            node = nodes.get(declared)
            if node is None or declared not in ("hp-odu", "hp-idu", "hp-ctrl-box"):
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: HpCommandNodeName "
                    f"{declared!r} is not an ShNode named hp-odu, hp-idu or hp-ctrl-box."
                )
            component_ids = {c.ComponentId for c in self.Components}
            if node.ComponentId is None or node.ComponentId not in component_ids:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} has no "
                    "ComponentId resolving to a Component."
                )
            if node.ActorClass != ActorClass.HpTwin:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} has "
                    f"ActorClass {node.ActorClass}, expected HpTwin."
                )
            hp_boss = nodes.get("hp-boss")
            boss_handle = (hp_boss.Handle or hp_boss.Name) if hp_boss is not None else None
            handle = node.Handle or node.Name
            if "." not in handle or handle.rsplit(".", 1)[0] != boss_handle:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} handle "
                    f"{handle!r} is not directly under hp-boss ({boss_handle!r})."
                )
        for n in self.ShNodes:
            if n.ActorClass == ActorClass.HpTwin and n.Name != declared:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {n.Name!r} has "
                    f"ActorClass HpTwin but HpCommandNodeName is {declared!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_11(self) -> "NolanLayout":
        """
        Axiom 11: PrefixClosedHandles.
        The authored handles are the initial command tree: every dot-separated
        prefix of an effective handle is the effective handle of some ShNode.
        """
        check_prefix_closed_handles(self.ShNodes, "Axiom 11 (PrefixClosedHandles)")
        return self

    @model_validator(mode="after")
    def check_axiom_12(self) -> "NolanLayout":
        """
        Axiom 12: ActuatorLeaves.
        a. Every actuator SHALL have a dotted effective handle and SHALL be a
        leaf. b. Every leaf SHALL be an actuator or a command node.
        """
        check_actuator_leaves(self.ShNodes, "Axiom 12 (ActuatorLeaves)")
        return self

    @model_validator(mode="after")
    def check_axiom_13(self) -> "NolanLayout":
        """
        Axiom 13: ZoneTempChannelResolution
        a. Every zone's TempChannelName in Hydronic.Zones SHALL equal the Name of a
        channel in DataChannels or in DerivedChannels.
        b. That channel SHALL carry temperature: a DataChannel's Quantity, or a
        DerivedChannel's OutputQuantity, SHALL be Temperature.
        """
        check_zone_temp_channel_resolution(
            self.Hydronic.Zones, self.DataChannels, self.DerivedChannels,
            "Axiom 13 (ZoneTempChannelResolution)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_14(self) -> "NolanLayout":
        """
        Axiom 14: CircuitWhitewireChannelResolution
        Every circuit's WhitewireChannelName in Hydronic.ZoneCallCircuits SHALL equal the Name
        of a channel in DataChannels.
        """
        check_circuit_whitewire_channel_resolution(
            self.Hydronic.ZoneCallCircuits, self.DataChannels,
            "Axiom 14 (CircuitWhitewireChannelResolution)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_15(self) -> "NolanLayout":
        """
        Axiom 15: CircuitHeatCallChannel
        For each circuit in Hydronic.ZoneCallCircuits, exactly one channel in DerivedChannels
        SHALL have Strategy "heat-call" and InputChannelNames equal to [the circuit's
        WhitewireChannelName].
        """
        check_circuit_heat_call_channel(
            self.Hydronic.ZoneCallCircuits, self.DerivedChannels,
            "Axiom 15 (CircuitHeatCallChannel)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_16(self) -> "NolanLayout":
        """
        Axiom 16: DerivedChannelCreatorResolution
        a. Every channel's CreatedByNodeName in DerivedChannels SHALL equal the Name of a
        ShNode in ShNodes.
        b. The ShNode named by a channel's CreatedByNodeName SHALL NOT have ActorClass
        "NoActor".
        """
        check_derived_channel_creator_resolution(
            self.ShNodes, self.DerivedChannels,
            "Axiom 16 (DerivedChannelCreatorResolution)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_17(self) -> "NolanLayout":
        """
        Axiom 17: DataChannelNodeResolution
        a. Every channel's AboutNodeName in DataChannels SHALL equal the Name of a ShNode in
        ShNodes.
        b. Every channel's CapturedByNodeName in DataChannels SHALL equal the Name of a ShNode
        in ShNodes.
        c. The ShNode named by a channel's CapturedByNodeName SHALL NOT have ActorClass
        "NoActor".
        """
        check_data_channel_node_resolution(
            self.ShNodes, self.DataChannels,
            "Axiom 17 (DataChannelNodeResolution)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_18(self) -> "NolanLayout":
        """
        Axiom 18: DerivedChannelInputsAcyclic
        a. Every name in a channel's InputChannelNames in DerivedChannels SHALL equal the Name
        of a channel in DataChannels or in DerivedChannels.
        b. No channel in DerivedChannels SHALL be reachable from itself by following
        InputChannelNames.
        """
        check_derived_channel_inputs_acyclic(
            self.DataChannels, self.DerivedChannels,
            "Axiom 18 (DerivedChannelInputsAcyclic)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_19(self) -> "NolanLayout":
        """
        Axiom 19: ChannelNameUniqueness
        The Names of the channels in DataChannels and DerivedChannels, taken together, SHALL be
        pairwise distinct.
        """
        check_channel_name_uniqueness(
            self.DataChannels, self.DerivedChannels,
            "Axiom 19 (ChannelNameUniqueness)",
        )
        return self

    @model_validator(mode="after")
    def check_axiom_20(self) -> "NolanLayout":
        """
        Axiom 20: BufferTank
        A Nolan home has a buffer tank. For each depth i in 1..3 a channel
        named "buffer-depth{i}" SHALL exist in DataChannels or in
        DerivedChannels.
        """
        channels = {c.Name for c in self.DataChannels} | {
            c.Name for c in self.DerivedChannels
        }
        missing = [
            f"buffer-depth{i}" for i in (1, 2, 3) if f"buffer-depth{i}" not in channels
        ]
        if missing:
            raise ValueError(
                f"Axiom 20 (BufferTank) failed: missing buffer channel(s) {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_21(self) -> "NolanLayout":
        """
        Axiom 21: StoreTankTemps
        For each tank index N in 1..Hydronic.TotalStoreTanks and each depth i in
        1..3, a channel named "tank{N}-depth{i}" SHALL exist in DataChannels or
        in DerivedChannels.
        """
        channels = {c.Name for c in self.DataChannels} | {
            c.Name for c in self.DerivedChannels
        }
        missing = [
            f"tank{tank}-depth{depth}"
            for tank in range(1, self.Hydronic.TotalStoreTanks + 1)
            for depth in (1, 2, 3)
            if f"tank{tank}-depth{depth}" not in channels
        ]
        if missing:
            raise ValueError(
                f"Axiom 21 (StoreTankTemps) failed: missing store tank channel(s) "
                f"{missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_22(self) -> "NolanLayout":
        """
        Axiom 22: SystemModelEnergyChannels
        DerivedChannels SHALL include channels named "usable-energy" and
        "required-energy", each with CreatedByNodeName "derived-generator" and
        Strategy "system-model". Parameters.EnergyModel.TypeName SHALL be
        gw0.usable.energy.layered on "usable-energy" and
        gw0.required.energy.layered on "required-energy".
        """
        expected_models = {
            "usable-energy": "gw0.usable.energy.layered",
            "required-energy": "gw0.required.energy.layered",
        }
        derived_by_name = {d.Name: d for d in self.DerivedChannels}
        for name, expected in expected_models.items():
            channel = derived_by_name.get(name)
            if channel is None:
                raise ValueError(
                    "Axiom 22 (SystemModelEnergyChannels) failed: "
                    f"DerivedChannel '{name}' is absent."
                )
            if channel.CreatedByNodeName != "derived-generator":
                raise ValueError(
                    "Axiom 22 (SystemModelEnergyChannels) failed: "
                    f"'{name}' must be created by 'derived-generator', got "
                    f"'{channel.CreatedByNodeName}'."
                )
            if channel.Strategy != "system-model":
                raise ValueError(
                    "Axiom 22 (SystemModelEnergyChannels) failed: "
                    f"'{name}' must use Strategy 'system-model', got "
                    f"'{channel.Strategy}'."
                )
            model = (channel.Parameters or {}).get("EnergyModel") or {}
            type_name = model.get("TypeName")
            if type_name != expected:
                raise ValueError(
                    "Axiom 22 (SystemModelEnergyChannels) failed: "
                    f"'{name}' must name EnergyModel '{expected}', got '{type_name}'."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_23(self) -> "NolanLayout":
        """
        Axiom 23: WebServerNode
        ShNodes SHALL contain exactly one node named "web-server", with
        ActorClass "NoActor".
        """
        matches = [node for node in self.ShNodes if node.Name == "web-server"]
        if len(matches) != 1 or matches[0].ActorClass != ActorClass.NoActor:
            raise ValueError(
                f"Axiom 23 (WebServerNode) failed: expected exactly one ShNode "
                f"'web-server' with ActorClass NoActor, got {matches}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_24(self) -> "NolanLayout":
        """
        Axiom 24: FloorLoopCircuitTemp
        a. Every circuit in Hydronic.ZoneCallCircuits whose EmitterType is
        "RadiantSlab" SHALL carry FloorTempChannelName. b. Where a circuit
        carries FloorTempChannelName, it SHALL equal the Name of a channel in
        DataChannels or in DerivedChannels, and that channel SHALL carry
        temperature: a DataChannel's Quantity, or a DerivedChannel's
        OutputQuantity, SHALL be Temperature.
        """
        quantity_by_name = {d.Name: d.Quantity for d in self.DataChannels}
        quantity_by_name.update(
            {d.Name: d.OutputQuantity for d in self.DerivedChannels}
        )
        for circuit in self.Hydronic.ZoneCallCircuits:
            floor_channel = circuit.FloorTempChannelName
            if floor_channel is None:
                if circuit.EmitterType == GwZoneEmitterType.RadiantSlab:
                    raise ValueError(
                        "Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                        f"{circuit.CircuitPosition} has EmitterType "
                        f"{circuit.EmitterType}, so it SHALL carry FloorTempChannelName."
                    )
                continue
            if floor_channel not in quantity_by_name:
                raise ValueError(
                    "Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                    f"{circuit.CircuitPosition} names FloorTempChannelName "
                    f"{floor_channel!r}, which is not a channel in DataChannels or "
                    "DerivedChannels."
                )
            if quantity_by_name[floor_channel] != Quantity.Temperature:
                raise ValueError(
                    "Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                    f"{circuit.CircuitPosition} names {floor_channel!r}, whose "
                    f"quantity is {quantity_by_name[floor_channel]}, not Temperature."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_25(self) -> "NolanLayout":
        """
        Axiom 25: DisabledNamesResolve
        Every name in DisabledNodeNames SHALL equal the Name of an ShNode in
        ShNodes, and every name in DisabledChannelNames SHALL equal the Name of
        a channel in DataChannels or in DerivedChannels.
        """
        node_names = {node.Name for node in self.ShNodes}
        channel_names = {c.Name for c in self.DataChannels} | {
            c.Name for c in self.DerivedChannels
        }
        for name in self.DisabledNodeNames:
            if name not in node_names:
                raise ValueError(
                    "Axiom 25 (DisabledNamesResolve) failed: "
                    f"DisabledNodeNames names '{name}', which is no ShNode."
                )
        for name in self.DisabledChannelNames:
            if name not in channel_names:
                raise ValueError(
                    "Axiom 25 (DisabledNamesResolve) failed: "
                    f"DisabledChannelNames names '{name}', which is no channel."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_26(self) -> "NolanLayout":
        """
        Axiom 26: DisabledNodesAreSensors
        Every name in DisabledNodeNames SHALL be the CapturedByNodeName of at
        least one DataChannel, and every DataChannel whose CapturedByNodeName
        is in DisabledNodeNames SHALL have its Name in DisabledChannelNames.
        """
        disabled_nodes = set(self.DisabledNodeNames)
        disabled_channels = set(self.DisabledChannelNames)
        capturing = {c.CapturedByNodeName for c in self.DataChannels}
        for name in disabled_nodes:
            if name not in capturing:
                raise ValueError(
                    "Axiom 26 (DisabledNodesAreSensors) failed: "
                    f"'{name}' captures no DataChannel."
                )
        for c in self.DataChannels:
            if c.CapturedByNodeName in disabled_nodes and c.Name not in disabled_channels:
                raise ValueError(
                    "Axiom 26 (DisabledNodesAreSensors) failed: "
                    f"'{c.Name}' is captured by disabled node "
                    f"'{c.CapturedByNodeName}' but is not in DisabledChannelNames."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_27(self) -> "NolanLayout":
        """
        Axiom 27: EnabledDerivedChannelsHaveLiveInputs
        Every DerivedChannel whose Name is not in DisabledChannelNames SHALL
        have no name in its InputChannelNames that is in DisabledChannelNames.
        """
        disabled = set(self.DisabledChannelNames)
        for d in self.DerivedChannels:
            if d.Name in disabled:
                continue
            dead = [name for name in d.InputChannelNames if name in disabled]
            if dead:
                raise ValueError(
                    f"Axiom 27 (EnabledDerivedChannelsHaveLiveInputs) failed: "
                    f"'{d.Name}' is enabled but reads disabled inputs {dead}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_28(self) -> "NolanLayout":
        """
        Axiom 28: ActuatorChannels
        a. Every ShNode RequiredActuators names — the listed relays and 0-10V
        outputs, and each circuit's FailsafeRelayNode and OpsRelayNode — has a
        DataChannel of the same Name, about and captured by that node.
        b. That channel's TelemetryName is RelayState for a Relay and
        VoltsTimesTen for a ZeroTenOutputer.
        """
        relays = [
            "vdc-relay",
            "iso-valve-relay",
            "secondary-pump-relay",
            "hp-scada-ops-relay",
            "charge-valve-relay",
            "store-pump-relay",
            "buffer-top-elt-relay",
            "buffer-bottom-elt-relay",
            "tank1-top-elt-relay",
            "tank1-bottom-elt-relay",
        ]
        for circuit in self.Hydronic.ZoneCallCircuits or []:
            relays.extend((circuit.FailsafeRelayNode, circuit.OpsRelayNode))
        outputs = ["secondary-010v"]
        channel_by_name = {c.Name: c for c in (self.DataChannels or [])}
        for name, telemetry in [(r, TelemetryName.RelayState) for r in relays] + [
            (o, TelemetryName.VoltsTimesTen) for o in outputs
        ]:
            channel = channel_by_name.get(name)
            if channel is None:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: actuator '{name}' has no "
                    "DataChannel of the same Name."
                )
            if channel.AboutNodeName != name or channel.CapturedByNodeName != name:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: channel '{name}' is about "
                    f"'{channel.AboutNodeName}', captured by "
                    f"'{channel.CapturedByNodeName}'; both SHALL be '{name}'."
                )
            if channel.TelemetryName != telemetry:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: channel '{name}' has "
                    f"TelemetryName {channel.TelemetryName}, not {telemetry.value}."
                )
        return self


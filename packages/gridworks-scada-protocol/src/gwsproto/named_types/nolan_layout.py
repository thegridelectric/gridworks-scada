from collections import Counter
from typing import List, Literal

from pydantic import ConfigDict, model_validator

from gwsproto.enums import ActorClass
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
from gwsproto.named_types.i2c_dac_writer_component_gt import I2cDacWriterComponentGt
from gwsproto.named_types.i2c_multichannel_dt_relay_component_gt import (
    I2cMultichannelDtRelayComponentGt,
)
from gwsproto.named_types.i2c_relay_component_gt import I2cRelayComponentGt
from gwsproto.named_types.i2c_thermistor_reader_component_gt import (
    I2cThermistorReaderComponentGt,
)
from gwsproto.named_types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from gwsproto.named_types.pico_tank_module_component_gt import PicoTankModuleComponentGt
from gwsproto.named_types.scada_board_component_gt import ScadaBoardComponentGt
from gwsproto.named_types.sim_dac_writer_component_gt import SimDacWriterComponentGt
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.sim_relay_component_gt import SimRelayComponentGt
from gwsproto.named_types.sim_sensor_component_gt import SimSensorComponentGt
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt
from gwsproto.type_helpers.command_tree_axioms import (
    check_actuator_leaves,
    check_prefix_closed_handles,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType

# The component types a Nolan (gw108) layout may contain (mirrors the sema draft oneOf).
NolanComponent = (
    DeviceComponentGt
    | ElectricMeterComponentGt
    | GpioSensorComponentGt
    | GpioRelayComponentGt
    | I2cDacWriterComponentGt
    | I2cMultichannelDtRelayComponentGt
    | I2cRelayComponentGt
    | I2cThermistorReaderComponentGt
    | PicoBtuMeterComponentGt
    | PicoTankModuleComponentGt
    | ScadaBoardComponentGt
    | SimDacWriterComponentGt
    | SimPicoTankModuleComponentGt
    | SimRelayComponentGt
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

        For every board-resident component in Components (gpio.sensor.component.gt,
        gpio.relay.component.gt, i2c.thermistor.reader.component.gt): its
        BoardComponentId SHALL equal the ComponentId of a scada.board.component.gt in
        Components; that board component's DeviceType SHALL match the DeviceType of a
        gw1.scada.device.type.gt record in DeviceTypes; and the component's board name
        SHALL match a Name in that record.
        """
        boards = {
            c.ComponentId: c for c in self.Components
            if c.TypeName == "scada.board.component.gt"
        }
        records = {
            r.DeviceType: r for r in self.DeviceTypes
            if isinstance(r, ScadaDeviceTypeGt)
        }
        kinds = {
            "gpio.sensor.component.gt": ("GpioName", "NativeGpioInputs"),
            "gpio.relay.component.gt": ("GpioName", "NativeGpioOutputs"),
            "i2c.thermistor.reader.component.gt": ("AdcName", "ThermistorAdcs"),
        }
        for c in self.Components:
            kind = kinds.get(c.TypeName)
            if kind is None:
                continue
            attr, list_name = kind
            board = boards.get(c.BoardComponentId)
            if board is None:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: BoardComponentId "
                    f"'{c.BoardComponentId}' of component '{c.ComponentId}' does "
                    "not resolve to a scada.board.component.gt."
                )
            record = records.get(board.DeviceType)
            if record is None:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: board DeviceType "
                    f"'{board.DeviceType}' has no gw1.scada.device.type.gt record."
                )
            names = {e.Name for e in (getattr(record, list_name) or [])}
            wanted = getattr(c, attr)
            if wanted not in names:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: name "
                    f"'{wanted}' of component '{c.ComponentId}' is not in the "
                    f"board record's {list_name}."
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

        ShNodes SHALL contain "n" (NoActor), "pico-cycler" (PicoCycler) and
        "hp-boss" (HpBoss), with no additional ShNode of those Names; the
        effective handle of "n" SHALL be "auto.lc.n".
        """
        pairs = (
            ("n", ActorClass.NoActor),
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

        a. ShNodes SHALL include the plant relays "iso-valve-relay",
        "secondary-pump-relay", "hp-scada-ops-relay", "charge-valve-relay",
        "store-pump-relay", "buffer-top-elt-relay", "buffer-bottom-elt-relay",
        "tank1-top-elt-relay", and "tank1-bottom-elt-relay", each with
        ActorClass "Relay".
        b. Hydronic.ZoneCallCircuits SHALL be non-empty, and each circuit's
        FailsafeRelayNode and OpsRelayNode SHALL name a ShNode in ShNodes
        with ActorClass "Relay".
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
                "secondary-lwt", "secondary-ewt",
                "dist-flow", "primary-flow", "store-flow", "secondary-flow",
                "buffer-depth1-device", "buffer-depth2-device", "buffer-depth3-device",
                "tank1-depth1-device", "tank1-depth2-device", "tank1-depth3-device",
                "hp-odu-pwr", "hp-ctrl-box-pwr",
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

from typing import Literal, Self
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.types.ads111x_based_device_type_gt import (
    Ads111xBasedDeviceTypeGt,
)
from sema_snapshot.sema.types.data_channel_gt import DataChannelGt
from sema_snapshot.sema.types.derived_channel_gt import DerivedChannelGt
from sema_snapshot.sema.types.device_component_gt import DeviceComponentGt
from sema_snapshot.sema.types.electric_meter_component_gt import (
    ElectricMeterComponentGt,
)
from sema_snapshot.sema.types.electric_meter_device_type_gt import (
    ElectricMeterDeviceTypeGt,
)
from sema_snapshot.sema.types.g_node_gt import GNodeGt
from sema_snapshot.sema.types.gpio_relay_component_gt import GpioRelayComponentGt
from sema_snapshot.sema.types.gpio_sensor_component_gt import GpioSensorComponentGt
from sema_snapshot.sema.types.hp_control_box_device_type_gt import (
    HpControlBoxDeviceTypeGt,
)
from sema_snapshot.sema.types.hp_device_type_gt import HpDeviceTypeGt
from sema_snapshot.sema.types.hydronic import Hydronic
from sema_snapshot.sema.types.i2c_dac_output_component_gt import I2cDacOutputComponentGt
from sema_snapshot.sema.types.i2c_relay_component_gt import I2cRelayComponentGt
from sema_snapshot.sema.types.i2c_thermistor_reader_component_gt import (
    I2cThermistorReaderComponentGt,
)
from sema_snapshot.sema.types.pico_btu_meter_component_gt import PicoBtuMeterComponentGt
from sema_snapshot.sema.types.pico_tank_module_component_gt import (
    PicoTankModuleComponentGt,
)
from sema_snapshot.sema.types.scada_board_component_gt import ScadaBoardComponentGt
from sema_snapshot.sema.types.scada_device_type_gt import ScadaDeviceTypeGt
from sema_snapshot.sema.types.sim_pico_btu_meter_component_gt import (
    SimPicoBtuMeterComponentGt,
)
from sema_snapshot.sema.types.sim_pico_flow_module_component_gt import (
    SimPicoFlowModuleComponentGt,
)
from sema_snapshot.sema.types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from sema_snapshot.sema.types.sim_sensor_component_gt import SimSensorComponentGt
from sema_snapshot.sema.types.spaceheat_node_gt import SpaceheatNodeGt
from sema_snapshot.sema.types.web_server_component_gt import WebServerComponentGt


class NolanLayout(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.nolan.layout/000"""

    g_nodes: list[GNodeGt]
    sh_nodes: list[SpaceheatNodeGt]
    data_channels: list[DataChannelGt]
    derived_channels: list[DerivedChannelGt]
    components: list[
        DeviceComponentGt
        | ElectricMeterComponentGt
        | GpioSensorComponentGt
        | GpioRelayComponentGt
        | I2cDacOutputComponentGt
        | I2cRelayComponentGt
        | I2cThermistorReaderComponentGt
        | ScadaBoardComponentGt
        | PicoBtuMeterComponentGt
        | PicoTankModuleComponentGt
        | SimPicoBtuMeterComponentGt
        | SimPicoFlowModuleComponentGt
        | SimPicoTankModuleComponentGt
        | SimSensorComponentGt
        | WebServerComponentGt
    ]
    device_types: list[
        ElectricMeterDeviceTypeGt
        | Ads111xBasedDeviceTypeGt
        | ScadaDeviceTypeGt
        | HpDeviceTypeGt
        | HpControlBoxDeviceTypeGt
    ]
    hydronic: Hydronic
    disabled_node_names: list[SpaceheatName]
    disabled_channel_names: list[SpaceheatName]
    type_name: Literal["gw.nolan.layout"] = "gw.nolan.layout"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "NolanLayout":
        """
        Axiom 1: TransactivePowerChannel DerivedChannels SHALL contain exactly one channel
        whose Strategy is "transactive-power" — the metered transactive boundary, computed by
        the power-meter actor (not the derived-generator). Each name in that channel's
        InputChannelNames SHALL resolve to an existing DataChannel with TelemetryName
        "PowerW", and the AboutNode of each such DataChannel SHALL carry a NameplatePowerW. No
        name in that channel's InputChannelNames SHALL be in DisabledChannelNames. (The
        metered set is declared once here, replacing the former per-node InPowerMetering flag;
        the NameplatePowerW obligation folds in spaceheat.node.gt's retired
        InPowerMetering-requires-nameplate axiom.)
        """
        transactive = [
            d
            for d in (self.derived_channels or [])
            if d.strategy == "transactive-power"
        ]
        if len(transactive) != 1:
            raise ValueError(
                "Axiom 1 (TransactivePowerChannel) failed: expected exactly one "
                f"transactive-power DerivedChannel, found {len(transactive)}."
            )
        data_by_name = {d.name: d for d in (self.data_channels or [])}
        node_by_name = {n.name: n for n in (self.sh_nodes or [])}
        for name in transactive[0].input_channel_names:
            ch = data_by_name.get(name)
            if ch is None:
                raise ValueError(
                    f"Axiom 1 (TransactivePowerChannel) failed: input '{name}' is not a DataChannel."
                )
            if ch.telemetry_name != "PowerW":
                raise ValueError(
                    f"Axiom 1 (TransactivePowerChannel) failed: input '{name}' must be PowerW, "
                    f"got '{ch.telemetry_name}'."
                )
            node = node_by_name.get(ch.about_node_name)
            if node is None or node.nameplate_power_w is None:
                raise ValueError(
                    f"Axiom 1 (TransactivePowerChannel) failed: about-node "
                    f"'{ch.about_node_name}' of input '{name}' has no NameplatePowerW."
                )
        disabled = set(self.disabled_channel_names)
        for name in transactive[0].input_channel_names:
            if name in disabled:
                raise ValueError(
                    f"Axiom 1 (TransactivePowerChannel) failed: input '{name}' is in "
                    "DisabledChannelNames."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "NolanLayout":
        """
        Axiom 2: BoardResolution For every component in Components carrying a
        BoardComponentId (board-resident by that fact alone, whatever its TypeName): its
        BoardComponentId SHALL equal the ComponentId of a scada.board.component.gt in
        Components; that board component's DeviceType SHALL match the DeviceType of a
        gw1.scada.device.type.gt record in DeviceTypes; and the component's board name
        (GpioName against NativeGpioInputs for sensors, GpioName against
        NativeGpioOutputs for relays, AdcName against the ThermistorAdcs Names for
        thermistor readers, RelayName against the I2cRelays RelayNames for i2c relays,
        DacName against the Dacs DacNames for DAC outputs) SHALL match a Name in that
        record.
        """
        boards = {
            c.component_id: c
            for c in (self.components or [])
            if c.type_name == "scada.board.component.gt"
        }
        records = {
            r.device_type: r
            for r in (self.device_types or [])
            if r.type_name == "gw1.scada.device.type.gt"
        }
        kinds = {
            "gpio.sensor.component.gt": ("gpio_name", "native_gpio_inputs", "name"),
            "gpio.relay.component.gt": ("gpio_name", "native_gpio_outputs", "name"),
            "i2c.thermistor.reader.component.gt": (
                "adc_name",
                "thermistor_adcs",
                "name",
            ),
            "i2c.relay.component.gt": ("relay_name", "i2c_relays", "relay_name"),
            "i2c.dac.output.component.gt": ("dac_name", "dacs", "dac_name"),
        }
        for c in self.components or []:
            if "board_component_id" not in type(c).model_fields:
                continue
            kind = kinds.get(c.type_name)
            if kind is None:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: component "
                    f"'{c.component_id}' ({c.type_name}) carries a BoardComponentId "
                    "but the board-name table has no entry for its kind."
                )
            attr, list_name, entry_attr = kind
            board = boards.get(c.board_component_id)
            if board is None:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: BoardComponentId "
                    f"'{c.board_component_id}' of component '{c.component_id}' does "
                    "not resolve to a scada.board.component.gt."
                )
            record = records.get(board.device_type)
            if record is None:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: board DeviceType "
                    f"'{board.device_type}' has no gw1.scada.device.type.gt record."
                )
            wanted = getattr(c, attr)
            names = {getattr(e, entry_attr) for e in (getattr(record, list_name) or [])}
            if wanted not in names:
                raise ValueError(
                    "Axiom 2 (BoardResolution) failed: name "
                    f"'{wanted}' of component '{c.component_id}' is not in the "
                    f"board record's {list_name}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "NolanLayout":
        """
        Axiom 3: CoreShNodesExistenceAndActorClass ShNodes SHALL contain a node with
        each of the following Name / ActorClass pairs, and no additional ShNode with any
        of these Names SHALL exist: "s" → ActorClass "PrimaryScada" "s2" → ActorClass
        "SecondaryScada" "power-meter" → ActorClass "PowerMeter" "ltn" → ActorClass
        "NoActor" "admin" → ActorClass "NoActor" "auto" → ActorClass "NoActor" "la" →
        ActorClass "LeafAlly" "lc" → ActorClass "LocalControl" "derived-generator" →
        ActorClass "DerivedGenerator" "cold-watch" → ActorClass "ColdWatch" The effective
        handle (Handle if present, otherwise Name) of "admin" SHALL be "admin" and of
        "auto" SHALL be "auto".
        """
        pairs = (
            ("s", "PrimaryScada"),
            ("s2", "SecondaryScada"),
            ("power-meter", "PowerMeter"),
            ("ltn", "NoActor"),
            ("admin", "NoActor"),
            ("auto", "NoActor"),
            ("la", "LeafAlly"),
            ("lc", "LocalControl"),
            ("derived-generator", "DerivedGenerator"),
            ("cold-watch", "ColdWatch"),
        )
        nodes = [n for n in (self.sh_nodes or [])]
        for name, actor_class in pairs:
            matches = [n for n in nodes if n.name == name]
            if len(matches) != 1:
                raise ValueError(
                    "Axiom 3 (CoreShNodesExistenceAndActorClass) failed: expected exactly "
                    f"one ShNode named {name!r}, found {len(matches)}."
                )
            if str(matches[0].actor_class) != actor_class:
                raise ValueError(
                    "Axiom 3 (CoreShNodesExistenceAndActorClass) failed: ShNode "
                    f"{name!r} has ActorClass {matches[0].actor_class}, expected {actor_class}."
                )
        for name, handle in (("admin", "admin"), ("auto", "auto")):
            node = next(n for n in nodes if n.name == name)
            effective = node.handle if node.handle is not None else node.name
            if effective != handle:
                raise ValueError(
                    "Axiom 3 (CoreShNodesExistenceAndActorClass) failed: "
                    f"{name!r} effective handle is {effective!r}, expected {handle!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_4(self) -> "NolanLayout":
        """
        Axiom 4: CommandNodesExistenceAndActorClass a. ShNodes SHALL contain a node with
        each of the following Name / ActorClass pairs, and no additional ShNode with any
        of these Names SHALL exist: "n" → ActorClass "NoActor" "cold-override" →
        ActorClass "NoActor" "scada-blind" → ActorClass "NoActor" "standby" → ActorClass
        "NoActor" "five-v-boss" → ActorClass "FiveVBoss" "pico-cycler" → ActorClass
        "PicoCycler" "hp-boss" → ActorClass "HpBoss" (hp-boss is a command node in every
        layout: hp-scada-ops-relay reports to it in all states, dormant when no heat
        pump is commandable.) b. If Hydronic.Backup is present, ShNodes SHALL contain
        exactly one node named "backup", with ActorClass "NoActor". c. If
        Hydronic.Backup is absent, no ShNode SHALL be named "backup".
        """
        pairs = (
            ("n", "NoActor"),
            ("cold-override", "NoActor"),
            ("scada-blind", "NoActor"),
            ("standby", "NoActor"),
            ("five-v-boss", "FiveVBoss"),
            ("pico-cycler", "PicoCycler"),
            ("hp-boss", "HpBoss"),
        )
        nodes = [n for n in (self.sh_nodes or [])]
        for name, actor_class in pairs:
            matches = [n for n in nodes if n.name == name]
            if len(matches) != 1:
                raise ValueError(
                    "Axiom 4 (CommandNodesExistenceAndActorClass) failed: expected exactly "
                    f"one ShNode named {name!r}, found {len(matches)}."
                )
            if str(matches[0].actor_class) != actor_class:
                raise ValueError(
                    "Axiom 4 (CommandNodesExistenceAndActorClass) failed: ShNode "
                    f"{name!r} has ActorClass {matches[0].actor_class}, expected {actor_class}."
                )
        backups = [n for n in (self.sh_nodes or []) if n.name == "backup"]
        if self.hydronic.backup is not None:
            if len(backups) != 1 or str(backups[0].actor_class) != "NoActor":
                raise ValueError(
                    "Axiom 4 (CommandNodesExistenceAndActorClass) failed: Hydronic.Backup "
                    "is present, so exactly one ShNode 'backup' with ActorClass NoActor "
                    "SHALL exist."
                )
        elif backups:
            raise ValueError(
                "Axiom 4 (CommandNodesExistenceAndActorClass) failed: Hydronic.Backup "
                "is absent, so no ShNode SHALL be named 'backup'."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "NolanLayout":
        """
        Axiom 5: RequiredActuators a. ShNodes SHALL include nodes named "vdc-relay",
        "iso-valve-relay", "secondary-pump-relay", "hp-scada-ops-relay",
        "charge-valve-relay", "store-pump-relay", "buffer-top-elt-relay",
        "buffer-bottom-elt-relay", "tank1-top-elt-relay", and "tank1-bottom-elt-relay",
        each with ActorClass "Relay". b. Each circuit's FailsafeRelayNode and
        OpsRelayNode in Hydronic.ZoneCallCircuits SHALL name a ShNode in ShNodes with
        ActorClass "Relay". c. ShNodes SHALL include a node named
        "secondary-010v" with ActorClass "ZeroTenOutputer" and a ComponentId equal to
        the ComponentId of an i2c.dac.output.component.gt in Components.
        """
        actor_class_by_name = {
            n.name: str(n.actor_class) for n in (self.sh_nodes or [])
        }

        def relay_or_raise(node_name: str, role: str) -> None:
            actor_class = actor_class_by_name.get(node_name)
            if actor_class is None:
                raise ValueError(
                    f"Axiom 5 (RequiredActuators) failed: no ShNode named {node_name} ({role})."
                )
            if actor_class != "Relay":
                raise ValueError(
                    f"Axiom 5 (RequiredActuators) failed: {node_name} ({role}) has "
                    f"ActorClass {actor_class}, not Relay."
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
        for circuit in self.hydronic.zone_call_circuits:
            relay_or_raise(circuit.failsafe_relay_node, "circuit failsafe relay")
            relay_or_raise(circuit.ops_relay_node, "circuit ops relay")
        output_node = next(
            (n for n in (self.sh_nodes or []) if n.name == "secondary-010v"), None
        )
        if output_node is None:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: no ShNode named secondary-010v."
            )
        if str(output_node.actor_class) != "ZeroTenOutputer":
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: secondary-010v has ActorClass "
                f"{output_node.actor_class}, not ZeroTenOutputer."
            )
        dac_output_ids = {
            c.component_id
            for c in (self.components or [])
            if isinstance(c, I2cDacOutputComponentGt)
        }
        if output_node.component_id not in dac_output_ids:
            raise ValueError(
                "Axiom 5 (RequiredActuators) failed: secondary-010v ComponentId "
                f"{output_node.component_id} is not an i2c.dac.output.component.gt in Components."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "NolanLayout":
        """
        Axiom 6: RequiredHeatpumpEquipment ShNodes SHALL include nodes named "hp-odu"
        and "hp-ctrl-box" (a Nolan home is a monobloc), each with a ComponentId equal to
        the ComponentId of a Component in Components, and each with ActorClass "NoActor"
        unless it is the node Hydronic.HpCommandNodeName names, whose ActorClass
        CommandableHeatPump governs.
        """
        component_ids = {c.component_id for c in (self.components or [])}
        nodes = {n.name: n for n in (self.sh_nodes or [])}
        for name in ("hp-odu", "hp-ctrl-box"):
            node = nodes.get(name)
            if node is None:
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: no ShNode named {name!r}."
                )
            if node.component_id is None or node.component_id not in component_ids:
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: {name!r} has no "
                    "ComponentId resolving to a Component."
                )
            if name == self.hydronic.hp_command_node_name:
                continue  # ActorClass governed by CommandableHeatPump
            if str(node.actor_class) != "NoActor":
                raise ValueError(
                    f"Axiom 6 (RequiredHeatpumpEquipment) failed: {name!r} has ActorClass "
                    f"{node.actor_class}, expected NoActor."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> "NolanLayout":
        """
        Axiom 7: ComponentBinding Every Component in Components SHALL have its
        ComponentId referenced by exactly one ShNode in ShNodes. The node's Name is the
        component's identity within the house; the ComponentId is the replaceable
        instance under it (a swapped part keeps the name and gets a fresh id).
        """
        refs: dict[str, int] = {}
        for n in self.sh_nodes or []:
            if n.component_id is not None:
                refs[n.component_id] = refs.get(n.component_id, 0) + 1
        violations = {
            c.component_id: refs.get(c.component_id, 0)
            for c in (self.components or [])
            if refs.get(c.component_id, 0) != 1
        }
        if violations:
            raise ValueError(
                "Axiom 7 (ComponentBinding) failed: components not referenced by exactly "
                f"one ShNode (id: reference count) {violations}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_8(self) -> "NolanLayout":
        """
        Axiom 8: RequiredSensing For each of the names "hp-lwt", "hp-ewt", "dist-swt",
        "dist-rwt", "store-hot-pipe", "store-cold-pipe", "secondary-lwt",
        "secondary-ewt", "buffer-cold-pipe", "fancoil-swt", "fancoil-rwt", "floor-swt",
        "floor-rwt", "dist-flow", "primary-flow", "store-flow", "secondary-flow",
        "hp-odu-pwr", "hp-ctrl-box-pwr", "primary-pump-pwr", "store-pump-pwr",
        "dist-pump-pwr", "secondary-pump-pwr", "buffer-top-elt-pwr",
        "buffer-bottom-elt-pwr", "tank1-top-elt-pwr", and "tank1-bottom-elt-pwr": a
        channel with that Name SHALL exist in DataChannels or in DerivedChannels.
        (Kind-agnostic by design: a name may migrate from raw DataChannel to same-name
        DerivedChannel without touching this contract.)
        """
        channel_names = {c.name for c in (self.data_channels or [])} | {
            c.name for c in (self.derived_channels or [])
        }
        missing = [
            name
            for name in (
                "hp-lwt",
                "hp-ewt",
                "dist-swt",
                "dist-rwt",
                "store-hot-pipe",
                "store-cold-pipe",
                "secondary-lwt",
                "secondary-ewt",
                "buffer-cold-pipe",
                "fancoil-swt",
                "fancoil-rwt",
                "floor-swt",
                "floor-rwt",
                "dist-flow",
                "primary-flow",
                "store-flow",
                "secondary-flow",
                "hp-odu-pwr",
                "hp-ctrl-box-pwr",
                "primary-pump-pwr",
                "store-pump-pwr",
                "dist-pump-pwr",
                "secondary-pump-pwr",
                "buffer-top-elt-pwr",
                "buffer-bottom-elt-pwr",
                "tank1-top-elt-pwr",
                "tank1-bottom-elt-pwr",
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
        """
        Axiom 9: SingleStoreTank Hydronic.WaterStore SHALL be present and its
        TotalStoreTanks SHALL equal 1: the Nolan plant carries exactly one store
        tank.
        """
        water_store = self.hydronic.water_store
        if water_store is None:
            raise ValueError(
                "Axiom 9 (SingleStoreTank) failed: Hydronic.WaterStore is absent."
            )
        if water_store.total_store_tanks != 1:
            raise ValueError(
                "Axiom 9 (SingleStoreTank) failed: TotalStoreTanks is "
                f"{water_store.total_store_tanks}, expected 1."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_10(self) -> "NolanLayout":
        """
        Axiom 10: CommandableHeatPump a. If Hydronic.HpCommandNodeName is present, it
        SHALL equal the Name of a ShNode in ShNodes named "hp-odu", "hp-idu" or
        "hp-ctrl-box", whose ComponentId equals the ComponentId of a Component in
        Components, whose ActorClass is "HpTwin", and whose effective handle (Handle if
        present, otherwise Name) has the effective handle of the ShNode named "hp-boss"
        as its parent prefix. b. Every ShNode with ActorClass "HpTwin" SHALL be the node
        Hydronic.HpCommandNodeName names; when HpCommandNodeName is absent no ShNode
        SHALL have ActorClass "HpTwin".
        """
        declared = self.hydronic.hp_command_node_name
        nodes = {n.name: n for n in (self.sh_nodes or [])}
        if declared is not None:
            node = nodes.get(declared)
            if node is None or declared not in ("hp-odu", "hp-idu", "hp-ctrl-box"):
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: HpCommandNodeName {declared!r} "
                    "is not an ShNode named hp-odu, hp-idu or hp-ctrl-box."
                )
            component_ids = {c.component_id for c in (self.components or [])}
            if node.component_id is None or node.component_id not in component_ids:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} has no "
                    "ComponentId resolving to a Component."
                )
            if str(node.actor_class) != "HpTwin":
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} has ActorClass "
                    f"{node.actor_class}, expected HpTwin."
                )
            hp_boss = nodes.get("hp-boss")
            boss_handle = (
                (hp_boss.handle or hp_boss.name) if hp_boss is not None else None
            )
            handle = node.handle or node.name
            if (
                boss_handle is None
                or handle.rsplit(".", 1)[0] != boss_handle
                or "." not in handle
            ):
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {declared!r} handle {handle!r} "
                    f"is not directly under hp-boss ({boss_handle!r})."
                )
        for n in nodes.values():
            if str(n.actor_class) == "HpTwin" and n.name != declared:
                raise ValueError(
                    f"Axiom 10 (CommandableHeatPump) failed: {n.name!r} has ActorClass HpTwin "
                    f"but HpCommandNodeName is {declared!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_11(self) -> "NolanLayout":
        """
        Axiom 11: PrefixClosedHandles Let the effective handle of an ShNode be its
        Handle if present, otherwise its Name. The set of effective handles SHALL be
        prefix-closed: for every ShNode in ShNodes, each dot-separated prefix of its
        effective handle SHALL also be the effective handle of some ShNode in ShNodes.
        """
        effective = {
            node.handle if node.handle is not None else node.name
            for node in self.sh_nodes
        }
        for value in effective:
            segments = value.split(".")
            for n in range(1, len(segments)):
                prefix = ".".join(segments[:n])
                if prefix not in effective:
                    raise ValueError(
                        f"Axiom 11 failed: effective handle {value!r} has "
                        f"prefix {prefix!r} that is not the effective handle "
                        "of any ShNode."
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_12(self) -> "NolanLayout":
        """
        Axiom 12: ActuatorLeaves Let the effective handle of an ShNode be its Handle if
        present, otherwise its Name. A leaf is an ShNode whose effective handle contains
        a dot and is the parent prefix of no other effective handle. An actuator is an
        ShNode whose ActorClass is "Relay", "ZeroTenOutputer" or "HpTwin". A command
        node is an ShNode whose ActorClass is "LocalControl", "LeafAlly", "FiveVBoss",
        "PicoCycler" or "HpBoss", or whose ActorClass is "NoActor" and whose
        effective handle's parent prefix is the effective handle of an ShNode with
        ActorClass "LocalControl". Local control's state nodes are named for the values
        of gw2.lc.top.state in which local control holds the command tree: "n" for
        Normal, "backup" for InBackup, "cold-override" for ColdOverride, "scada-blind"
        for ScadaBlind and "standby" for Standby; Dormant has no node. a. Every actuator
        SHALL have a dotted effective handle and SHALL be a leaf. b. Every leaf SHALL be
        an actuator or a command node. c. Every ShNode with ActorClass "NoActor" whose
        effective handle's parent prefix is the effective handle of an ShNode with
        ActorClass "LocalControl" SHALL be one of these state nodes: "n", "backup",
        "cold-override", "scada-blind" or "standby".
        """
        actuator_classes = {"Relay", "ZeroTenOutputer", "HpTwin"}
        command_classes = {
            "LocalControl",
            "LeafAlly",
            "FiveVBoss",
            "PicoCycler",
            "HpBoss",
        }
        by_handle = {
            (node.handle if node.handle is not None else node.name): node
            for node in self.sh_nodes
        }
        handles = set(by_handle)
        lc_handles = {
            h for h, n in by_handle.items() if str(n.actor_class) == "LocalControl"
        }

        def is_leaf(handle: str) -> bool:
            return "." in handle and not any(
                other.startswith(handle + ".") for other in handles
            )

        for handle, node in by_handle.items():
            actor_class = str(node.actor_class)
            if actor_class in actuator_classes and not is_leaf(handle):
                raise ValueError(
                    f"Axiom 12 (ActuatorLeaves) failed: actuator {node.name!r} with "
                    f"handle {handle!r} is not a dotted-handle leaf."
                )
            if is_leaf(handle):
                parent = handle.rsplit(".", 1)[0]
                is_command = actor_class in command_classes or (
                    actor_class == "NoActor" and parent in lc_handles
                )
                if actor_class not in actuator_classes and not is_command:
                    raise ValueError(
                        f"Axiom 12 (ActuatorLeaves) failed: leaf {node.name!r} with "
                        f"handle {handle!r} (ActorClass {actor_class}) is neither an "
                        "actuator nor a command node."
                    )
            if (
                actor_class == "NoActor"
                and "." in handle
                and handle.rsplit(".", 1)[0] in lc_handles
                and node.name
                not in ("n", "backup", "cold-override", "scada-blind", "standby")
            ):
                raise ValueError(
                    f"Axiom 12 (ActuatorLeaves) failed: {node.name!r} with handle "
                    f"{handle!r} is a NoActor node under local control other than n, "
                    "backup, cold-override, scada-blind or standby."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_13(self) -> Self:
        """
        Axiom 13: CircuitTempChannelResolution a. Every circuit's TempChannelName in
        Hydronic.ZoneCallCircuits SHALL equal the Name of a channel in DataChannels or in
        DerivedChannels. b. That channel SHALL carry temperature: a DataChannel's
        Quantity, or a DerivedChannel's OutputQuantity, SHALL be Temperature.
        """
        if self.hydronic is None:
            return self
        quantity_by_name = {d.name: str(d.quantity) for d in (self.data_channels or [])}
        quantity_by_name.update(
            {d.name: str(d.output_quantity) for d in (self.derived_channels or [])}
        )
        for circuit in self.hydronic.zone_call_circuits or []:
            name = circuit.temp_channel_name
            if not name:
                continue
            if name not in quantity_by_name:
                raise ValueError(
                    "Axiom 13 (CircuitTempChannelResolution) failed: circuit "
                    f"{circuit.name!r} names TempChannelName {name!r}, "
                    "which is not a channel in DataChannels or DerivedChannels."
                )
            if quantity_by_name[name] != "Temperature":
                raise ValueError(
                    "Axiom 13 (CircuitTempChannelResolution) failed: circuit "
                    f"{circuit.name!r} names {name!r}, whose quantity is "
                    f"{quantity_by_name[name]}, not Temperature."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_14(self) -> Self:
        """
        Axiom 14: CircuitWhitewireChannelResolution Every circuit's WhitewireChannelName
        in Hydronic.ZoneCallCircuits SHALL equal the Name of a channel in DataChannels.
        """
        if self.hydronic is None:
            return self
        data_names = {d.name for d in (self.data_channels or [])}
        for circuit in self.hydronic.zone_call_circuits or []:
            if circuit.whitewire_channel_name not in data_names:
                raise ValueError(
                    "Axiom 14 (CircuitWhitewireChannelResolution) failed: circuit "
                    f"{circuit.circuit_position} names WhitewireChannelName "
                    f"{circuit.whitewire_channel_name!r}, which is not a channel in DataChannels."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_15(self) -> Self:
        """
        Axiom 15: CircuitHeatCallChannel For each circuit in Hydronic.ZoneCallCircuits,
        exactly one channel in DerivedChannels SHALL have Strategy "heat-call" and
        InputChannelNames equal to [the circuit's WhitewireChannelName].
        """
        if self.hydronic is None:
            return self
        for circuit in self.hydronic.zone_call_circuits or []:
            heat_calls = [
                d.name
                for d in (self.derived_channels or [])
                if d.strategy == "heat-call"
                and list(d.input_channel_names) == [circuit.whitewire_channel_name]
            ]
            if len(heat_calls) != 1:
                raise ValueError(
                    "Axiom 15 (CircuitHeatCallChannel) failed: circuit "
                    f"{circuit.circuit_position} needs exactly one heat-call DerivedChannel whose "
                    f"InputChannelNames is [{circuit.whitewire_channel_name!r}], found {heat_calls}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_16(self) -> Self:
        """
        Axiom 16: DerivedChannelCreatorResolution a. Every channel's CreatedByNodeName
        in DerivedChannels SHALL equal the Name of a ShNode in ShNodes. b. The ShNode
        named by a channel's CreatedByNodeName SHALL NOT have ActorClass "NoActor".
        """
        actor_class_by_name = {
            n.name: str(n.actor_class) for n in (self.sh_nodes or [])
        }
        for d in self.derived_channels or []:
            if d.created_by_node_name not in actor_class_by_name:
                raise ValueError(
                    "Axiom 16 (DerivedChannelCreatorResolution) failed (a): DerivedChannel "
                    f"{d.name!r} names CreatedByNodeName {d.created_by_node_name!r}, "
                    "which is not a ShNode in ShNodes."
                )
            if actor_class_by_name[d.created_by_node_name] == "NoActor":
                raise ValueError(
                    "Axiom 16 (DerivedChannelCreatorResolution) failed (b): DerivedChannel "
                    f"{d.name!r} is created by {d.created_by_node_name!r}, "
                    "whose ActorClass is NoActor."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_17(self) -> Self:
        """
        Axiom 17: DataChannelNodeResolution a. Every channel's AboutNodeName in
        DataChannels SHALL equal the Name of a ShNode in ShNodes. b. Every channel's
        CapturedByNodeName in DataChannels SHALL equal the Name of a ShNode in ShNodes.
        c. The ShNode named by a channel's CapturedByNodeName SHALL NOT have ActorClass
        "NoActor".
        """
        actor_class_by_name = {
            n.name: str(n.actor_class) for n in (self.sh_nodes or [])
        }
        for ch in self.data_channels or []:
            if ch.about_node_name not in actor_class_by_name:
                raise ValueError(
                    "Axiom 17 (DataChannelNodeResolution) failed (a): DataChannel "
                    f"{ch.name!r} names AboutNodeName {ch.about_node_name!r}, "
                    "which is not a ShNode in ShNodes."
                )
            if ch.captured_by_node_name not in actor_class_by_name:
                raise ValueError(
                    "Axiom 17 (DataChannelNodeResolution) failed (b): DataChannel "
                    f"{ch.name!r} names CapturedByNodeName {ch.captured_by_node_name!r}, "
                    "which is not a ShNode in ShNodes."
                )
            if actor_class_by_name[ch.captured_by_node_name] == "NoActor":
                raise ValueError(
                    "Axiom 17 (DataChannelNodeResolution) failed (c): DataChannel "
                    f"{ch.name!r} is captured by {ch.captured_by_node_name!r}, "
                    "whose ActorClass is NoActor."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_18(self) -> Self:
        """
        Axiom 18: DerivedChannelInputsAcyclic a. Every name in a channel's
        InputChannelNames in DerivedChannels SHALL equal the Name of a channel in
        DataChannels or in DerivedChannels. b. No channel in DerivedChannels SHALL be
        reachable from itself by following InputChannelNames.
        """
        data_names = {ch.name for ch in (self.data_channels or [])}
        inputs_by_name = {
            d.name: list(d.input_channel_names) for d in (self.derived_channels or [])
        }
        for name, inputs in inputs_by_name.items():
            for input_name in inputs:
                if input_name not in data_names and input_name not in inputs_by_name:
                    raise ValueError(
                        "Axiom 18 (DerivedChannelInputsAcyclic) failed (a): DerivedChannel "
                        f"{name!r} names input {input_name!r}, which is not a channel in "
                        "DataChannels or DerivedChannels."
                    )
        for start in inputs_by_name:
            seen: set[str] = set()
            frontier = [n for n in inputs_by_name[start] if n in inputs_by_name]
            while frontier:
                current = frontier.pop()
                if current == start:
                    raise ValueError(
                        "Axiom 18 (DerivedChannelInputsAcyclic) failed (b): DerivedChannel "
                        f"{start!r} is reachable from itself through InputChannelNames."
                    )
                if current in seen:
                    continue
                seen.add(current)
                frontier.extend(
                    n for n in inputs_by_name[current] if n in inputs_by_name
                )
        return self

    @model_validator(mode="after")
    def check_axiom_19(self) -> Self:
        """
        Axiom 19: ChannelNameUniqueness The Names of the channels in DataChannels and
        DerivedChannels, taken together, SHALL be pairwise distinct.
        """
        seen: set[str] = set()
        for name in [ch.name for ch in (self.data_channels or [])] + [
            d.name for d in (self.derived_channels or [])
        ]:
            if name in seen:
                raise ValueError(
                    "Axiom 19 (ChannelNameUniqueness) failed: more than one channel in "
                    f"DataChannels and DerivedChannels is named {name!r}."
                )
            seen.add(name)
        return self

    @model_validator(mode="after")
    def check_axiom_20(self) -> "NolanLayout":
        """
        Axiom 20: BufferTank A Nolan home has a buffer tank. For each depth i in 1..3 a
        channel named "buffer-depth{i}" SHALL exist in DataChannels or in
        DerivedChannels. (The family invariant lives here, in the word; scada code asks
        the layout and assumes nothing.)
        """
        channel_names = {c.name for c in (self.data_channels or [])} | {
            c.name for c in (self.derived_channels or [])
        }
        missing = [
            f"buffer-depth{depth}"
            for depth in (1, 2, 3)
            if f"buffer-depth{depth}" not in channel_names
        ]
        if missing:
            raise ValueError(
                f"Axiom 20 (BufferTank) failed: missing buffer channels {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_21(self) -> "NolanLayout":
        """
        Axiom 21: StoreTankTemps For each tank index N in
        1..Hydronic.WaterStore.TotalStoreTanks and each depth i in 1..3, a channel
        named "tank{N}-depth{i}" SHALL exist in DataChannels or in DerivedChannels.
        """
        water_store = self.hydronic.water_store
        if water_store is None:
            return self
        channel_names = {c.name for c in (self.data_channels or [])} | {
            c.name for c in (self.derived_channels or [])
        }
        missing = [
            f"tank{tank}-depth{depth}"
            for tank in range(1, water_store.total_store_tanks + 1)
            for depth in (1, 2, 3)
            if f"tank{tank}-depth{depth}" not in channel_names
        ]
        if missing:
            raise ValueError(
                f"Axiom 21 (StoreTankTemps) failed: missing store tank channels {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_23(self) -> "NolanLayout":
        """
        Axiom 23: WebServerNode ShNodes SHALL contain exactly one node named
        "web-server", with ActorClass "NoActor".
        """
        if not self.sh_nodes:
            return self
        matches = [n for n in self.sh_nodes if n.name == "web-server"]
        if len(matches) != 1 or matches[0].actor_class != "NoActor":
            raise ValueError(
                f"Axiom 23 (WebServerNode) failed: expected exactly one ShNode "
                f"'web-server' with ActorClass NoActor, got {matches}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_24(self) -> "NolanLayout":
        """
        Axiom 24: FloorLoopCircuitTemp a. Every circuit in Hydronic.ZoneCallCircuits
        whose EmitterType is "RadiantSlab" SHALL carry
        FloorTempChannelName. b. Where a circuit carries FloorTempChannelName, it SHALL
        equal the Name of a channel in DataChannels or in DerivedChannels, and that
        channel SHALL carry temperature: a DataChannel's Quantity, or a DerivedChannel's
        OutputQuantity, SHALL be Temperature.
        """
        # String comparison, not an enum import: ZoneEmitterType is not a field
        # enum of this type, and an absolute sema.runtime import would break
        # inside a restricted snapshot package.
        if self.hydronic is None:
            return self
        quantity_by_name = {d.name: str(d.quantity) for d in (self.data_channels or [])}
        quantity_by_name.update(
            {d.name: str(d.output_quantity) for d in (self.derived_channels or [])}
        )
        for circuit in self.hydronic.zone_call_circuits or []:
            floor_channel = circuit.floor_temp_channel_name
            if floor_channel is None:
                if str(circuit.emitter_type) == "RadiantSlab":
                    raise ValueError(
                        f"Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                        f"{circuit.circuit_position} has EmitterType "
                        f"{circuit.emitter_type}, so it SHALL carry FloorTempChannelName."
                    )
                continue
            if floor_channel not in quantity_by_name:
                raise ValueError(
                    f"Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                    f"{circuit.circuit_position} names FloorTempChannelName "
                    f"{floor_channel!r}, which is not a channel in DataChannels or "
                    "DerivedChannels."
                )
            quantity = quantity_by_name[floor_channel]
            if quantity != "Temperature":
                raise ValueError(
                    f"Axiom 24 (FloorLoopCircuitTemp) failed: circuit at position "
                    f"{circuit.circuit_position} names {floor_channel!r}, whose quantity is "
                    f"{quantity}, not Temperature."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_25(self) -> "NolanLayout":
        """
        Axiom 25: DisabledNamesResolve Every name in DisabledNodeNames SHALL equal the
        Name of an ShNode in ShNodes, and every name in DisabledChannelNames SHALL equal
        the Name of a channel in DataChannels or in DerivedChannels.
        """
        node_names = {n.name for n in (self.sh_nodes or [])}
        channel_names = {c.name for c in (self.data_channels or [])} | {
            c.name for c in (self.derived_channels or [])
        }
        for name in self.disabled_node_names:
            if name not in node_names:
                raise ValueError(
                    f"Axiom 25 (DisabledNamesResolve) failed: DisabledNodeNames names "
                    f"'{name}', which is no ShNode."
                )
        for name in self.disabled_channel_names:
            if name not in channel_names:
                raise ValueError(
                    f"Axiom 25 (DisabledNamesResolve) failed: DisabledChannelNames names "
                    f"'{name}', which is no channel."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_26(self) -> "NolanLayout":
        """
        Axiom 26: DisabledNodesAreSensors Every name in DisabledNodeNames SHALL be the
        CapturedByNodeName of at least one DataChannel and SHALL NOT be the Name of an ShNode
        whose ActorClass is "Relay" or "ZeroTenOutputer"; every DataChannel whose
        CapturedByNodeName is in DisabledNodeNames SHALL have its Name in
        DisabledChannelNames; and no name in DisabledChannelNames SHALL be the Name of a
        DataChannel whose CapturedByNodeName is such an ShNode. Disabling is a sensing
        concept; an actuator is wired or absent.
        """
        disabled_nodes = set(self.disabled_node_names)
        disabled_channels = set(self.disabled_channel_names)
        actuators = {
            n.name
            for n in (self.sh_nodes or [])
            if str(n.actor_class) in ("Relay", "ZeroTenOutputer")
        }
        capturing = {c.captured_by_node_name for c in (self.data_channels or [])}
        for name in disabled_nodes:
            if name not in capturing:
                raise ValueError(
                    f"Axiom 26 (DisabledNodesAreSensors) failed: '{name}' captures no "
                    "DataChannel."
                )
            if name in actuators:
                raise ValueError(
                    f"Axiom 26 (DisabledNodesAreSensors) failed: '{name}' is an actuator; "
                    "an actuator is wired or absent, never disabled."
                )
        for c in self.data_channels or []:
            if (
                c.captured_by_node_name in disabled_nodes
                and c.name not in disabled_channels
            ):
                raise ValueError(
                    f"Axiom 26 (DisabledNodesAreSensors) failed: '{c.name}' is captured by "
                    f"disabled node '{c.captured_by_node_name}' but is not in "
                    "DisabledChannelNames."
                )
            if c.name in disabled_channels and c.captured_by_node_name in actuators:
                raise ValueError(
                    f"Axiom 26 (DisabledNodesAreSensors) failed: '{c.name}' is captured by "
                    f"actuator '{c.captured_by_node_name}'; an actuator channel is never disabled."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_27(self) -> "NolanLayout":
        """
        Axiom 27: EnabledDerivedChannelsHaveLiveInputs Every DerivedChannel whose Name
        is not in DisabledChannelNames SHALL have no name in its InputChannelNames that
        is in DisabledChannelNames.
        """
        disabled = set(self.disabled_channel_names)
        for d in self.derived_channels or []:
            if d.name in disabled:
                continue
            dead = [n for n in (d.input_channel_names or []) if n in disabled]
            if dead:
                raise ValueError(
                    f"Axiom 27 (EnabledDerivedChannelsHaveLiveInputs) failed: '{d.name}' is "
                    f"enabled but reads disabled inputs {dead}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_28(self) -> Self:
        """
        Axiom 28: ActuatorChannels a. For every ShNode RequiredActuators names — the
        listed relays and 0-10V outputs, and each circuit's FailsafeRelayNode and
        OpsRelayNode — a DataChannel with the same Name SHALL exist, with AboutNodeName
        and CapturedByNodeName equal to that Name. b. That channel's TelemetryName SHALL
        be "RelayState" for a node with ActorClass "Relay" and "VoltsTimesTen" for a
        node with ActorClass "ZeroTenOutputer".
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
        for circuit in self.hydronic.zone_call_circuits or []:
            relays.extend((circuit.failsafe_relay_node, circuit.ops_relay_node))
        outputs = ["secondary-010v"]
        channel_by_name = {c.name: c for c in (self.data_channels or [])}
        for name, telemetry in [(r, "RelayState") for r in relays] + [
            (o, "VoltsTimesTen") for o in outputs
        ]:
            channel = channel_by_name.get(name)
            if channel is None:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: actuator '{name}' has no "
                    "DataChannel of the same Name."
                )
            if channel.about_node_name != name or channel.captured_by_node_name != name:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: channel '{name}' is about "
                    f"'{channel.about_node_name}', captured by "
                    f"'{channel.captured_by_node_name}'; both SHALL be '{name}'."
                )
            if str(channel.telemetry_name) != telemetry:
                raise ValueError(
                    f"Axiom 28 (ActuatorChannels) failed: channel '{name}' has "
                    f"TelemetryName {channel.telemetry_name}, not {telemetry}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_29(self) -> Self:
        """
        Axiom 29: PrimaryPumpRecordAgreement Let the joined records be the
        hp.device.type.gt and hp.control.box.device.type.gt records in DeviceTypes whose
        DeviceType equals the DeviceType of the Component that "hp-odu" or "hp-ctrl-box"
        binds. If Hydronic.PrimaryPumpOwner is "Scada", no joined record SHALL have
        PrimaryPumpFactoryInstalled true with PrimaryPumpOverridable false: a pump that
        ships inside the unit and cannot be overridden is under the unit's control.
        """
        if str(self.hydronic.primary_pump_owner) != "Scada":
            return self
        component_by_id = {c.component_id: c for c in (self.components or [])}
        device_types = set()
        for n in self.sh_nodes or []:
            if (
                n.name in ("hp-odu", "hp-ctrl-box")
                and n.component_id in component_by_id
            ):
                device_type = getattr(
                    component_by_id[n.component_id], "device_type", None
                )
                if device_type is not None:
                    device_types.add(device_type)
        for r in self.device_types or []:
            if not isinstance(r, (HpDeviceTypeGt, HpControlBoxDeviceTypeGt)):
                continue
            if r.device_type not in device_types:
                continue
            if r.primary_pump_factory_installed and not r.primary_pump_overridable:
                raise ValueError(
                    "Axiom 29 (PrimaryPumpRecordAgreement) failed: PrimaryPumpOwner "
                    f"is Scada but record {r.device_type!r} ships its primary pump "
                    "inside the unit with no override."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_30(self) -> Self:
        """
        Axiom 30: CommandNodeHandles Let the effective handle of an ShNode be its Handle
        if present, otherwise its Name. The authored tree is the plant with no one in
        charge: "auto" is the root, the command nodes and every actuator hang directly
        under it, and a fixed relay hangs under the interior node that owns it. The
        effective handles SHALL be: "five-v-boss" → "auto.five-v-boss" "pico-cycler" →
        "auto.five-v-boss.pico-cycler" "vdc-relay" →
        "auto.five-v-boss.pico-cycler.vdc-relay" "lc" → "auto.lc" "n" → "auto.lc.n"
        "backup" → "auto.lc.backup" "cold-override" → "auto.lc.cold-override"
        "scada-blind" → "auto.lc.scada-blind" "standby" → "auto.lc.standby" "hp-boss" →
        "auto.hp-boss" "hp-scada-ops-relay" → "auto.hp-boss.hp-scada-ops-relay"
        "secondary-pump-relay" → "auto.hp-boss.secondary-pump-relay" (hp-boss owns the
        secondary pump as it owns the call: the pump runs whenever the heat pump is
        called or sensed running, whoever holds the tree.) Every other ShNode whose
        ActorClass is Relay or ZeroTenOutputer SHALL have the effective handle
        "auto.<Name>".
        """
        expected = {
            "five-v-boss": "auto.five-v-boss",
            "pico-cycler": "auto.five-v-boss.pico-cycler",
            "vdc-relay": "auto.five-v-boss.pico-cycler.vdc-relay",
            "lc": "auto.lc",
            "n": "auto.lc.n",
            "backup": "auto.lc.backup",
            "cold-override": "auto.lc.cold-override",
            "scada-blind": "auto.lc.scada-blind",
            "standby": "auto.lc.standby",
            "hp-boss": "auto.hp-boss",
            "hp-scada-ops-relay": "auto.hp-boss.hp-scada-ops-relay",
            "secondary-pump-relay": "auto.hp-boss.secondary-pump-relay",
        }
        for n in self.sh_nodes or []:
            effective = n.handle if n.handle is not None else n.name
            if n.name in expected:
                want = expected[n.name]
            elif str(n.actor_class) in ("Relay", "ZeroTenOutputer"):
                want = f"auto.{n.name}"
            else:
                continue
            if effective != want:
                raise ValueError(
                    f"Axiom 30 (CommandNodeHandles) failed: {n.name!r} has effective "
                    f"handle {effective!r}, expected {want!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_31(self) -> Self:
        """
        Axiom 31: HeatCallChannelBelongsToCircuit Every channel in DerivedChannels whose
        Strategy is "heat-call" SHALL have InputChannelNames equal to [the
        WhitewireChannelName of exactly one circuit in Hydronic.ZoneCallCircuits]. With
        CircuitHeatCallChannel, the heat-call channels and the circuits are one to one.
        """
        whitewires = [
            c.whitewire_channel_name for c in self.hydronic.zone_call_circuits
        ]
        for d in self.derived_channels or []:
            if d.strategy != "heat-call":
                continue
            inputs = list(d.input_channel_names)
            if len(inputs) != 1 or whitewires.count(inputs[0]) != 1:
                raise ValueError(
                    f"Axiom 31 (HeatCallChannelBelongsToCircuit) failed: heat-call channel "
                    f"'{d.name}' has inputs {inputs}, not exactly one circuit's whitewire."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_32(self) -> Self:
        """
        Axiom 32: HpWatchNode ShNodes SHALL include a node named "hp-watch" with
        ActorClass "HpWatch".
        """
        node = next((n for n in self.sh_nodes or [] if n.name == "hp-watch"), None)
        if node is None or str(node.actor_class) != "HpWatch":
            raise ValueError(
                "Axiom 32 (HpWatchNode) failed: no ShNode named 'hp-watch' with "
                "ActorClass 'HpWatch'."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_33(self) -> Self:
        """
        Axiom 33: CircuitSetpointChannel a. Every circuit's SetpointChannelName in
        Hydronic.ZoneCallCircuits SHALL equal the Name of a channel in DataChannels or in
        DerivedChannels. b. That channel SHALL carry temperature: a DataChannel's
        Quantity, or a DerivedChannel's OutputQuantity, SHALL be Temperature. c. Where a
        circuit's SetpointSource is "Learned", its SetpointChannelName SHALL name a
        channel in DerivedChannels. d. That derived channel's InputChannelNames SHALL
        contain the circuit's TempChannelName and the Name of the circuit's heat-call
        channel (the CircuitHeatCallChannel axiom). e. That derived channel's Strategy
        SHALL be "simple-falling-edge-setpoint".
        """
        if self.hydronic is None:
            return self
        derived_by_name = {d.name: d for d in (self.derived_channels or [])}
        quantity_by_name = {d.name: str(d.quantity) for d in (self.data_channels or [])}
        quantity_by_name.update(
            {name: str(d.output_quantity) for name, d in derived_by_name.items()}
        )
        for circuit in self.hydronic.zone_call_circuits or []:
            name = circuit.setpoint_channel_name
            if not name:
                continue
            if name not in quantity_by_name:
                raise ValueError(
                    "Axiom 33 (CircuitSetpointChannel) failed: circuit "
                    f"{circuit.name!r} names SetpointChannelName {name!r}, "
                    "which is not a channel in DataChannels or DerivedChannels."
                )
            if quantity_by_name[name] != "Temperature":
                raise ValueError(
                    "Axiom 33 (CircuitSetpointChannel) failed: circuit "
                    f"{circuit.name!r} names {name!r}, whose quantity is "
                    f"{quantity_by_name[name]}, not Temperature."
                )
            # String comparison: the enum class name differs under a snapshot's
            # local names.
            if str(circuit.setpoint_source) != "Learned":
                continue
            if name not in derived_by_name:
                raise ValueError(
                    "Axiom 33 (CircuitSetpointChannel) failed: circuit "
                    f"{circuit.name!r} has SetpointSource Learned, so "
                    f"{name!r} SHALL be a channel in DerivedChannels."
                )
            inputs = list(derived_by_name[name].input_channel_names or [])
            heat_calls = [
                d.name
                for d in derived_by_name.values()
                if d.strategy == "heat-call"
                and list(d.input_channel_names or [])
                == [circuit.whitewire_channel_name]
            ]
            needed = [circuit.temp_channel_name, *heat_calls]
            missing = [n for n in needed if n not in inputs]
            if missing:
                raise ValueError(
                    "Axiom 33 (CircuitSetpointChannel) failed: circuit "
                    f"{circuit.name!r} learns its setpoint on {name!r}, whose "
                    f"InputChannelNames {inputs} lack {missing}."
                )
            strategy = derived_by_name[name].strategy
            if strategy != "simple-falling-edge-setpoint":
                raise ValueError(
                    "Axiom 33 (CircuitSetpointChannel) failed: circuit "
                    f"{circuit.name!r} learns its setpoint on {name!r}, whose "
                    f"Strategy is {strategy!r}, not 'simple-falling-edge-setpoint'."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_34(self) -> Self:
        """
        Axiom 34: ReadThermostatChannels Where a circuit's SetpointSource is
        "FromThermostat", the channels named by its SetpointChannelName and
        TempChannelName SHALL each be a channel in DataChannels whose CapturedByNodeName
        is the Name of an ShNode whose ComponentId equals the circuit's
        Thermostat.ComponentId.
        """
        if self.hydronic is None:
            return self
        captured_by = {
            d.name: d.captured_by_node_name for d in (self.data_channels or [])
        }
        component_of = {n.name: n.component_id for n in (self.sh_nodes or [])}
        for circuit in self.hydronic.zone_call_circuits or []:
            # String comparison: the enum class name differs under a snapshot's
            # local names.
            if str(circuit.setpoint_source) != "FromThermostat":
                continue
            for field, name in (
                ("SetpointChannelName", circuit.setpoint_channel_name),
                ("TempChannelName", circuit.temp_channel_name),
            ):
                if not name:
                    continue
                if name not in captured_by:
                    raise ValueError(
                        "Axiom 34 (ReadThermostatChannels) failed: circuit "
                        f"{circuit.name!r} reads its thermostat, so {field} {name!r} "
                        "SHALL be a channel in DataChannels."
                    )
                component_id = component_of.get(captured_by[name])
                if (
                    component_id is None
                    or component_id != circuit.thermostat.component_id
                ):
                    raise ValueError(
                        "Axiom 34 (ReadThermostatChannels) failed: circuit "
                        f"{circuit.name!r} names {field} {name!r}, captured by "
                        f"{captured_by[name]!r}, which is not the node of the circuit's "
                        "thermostat component."
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_35(self) -> "NolanLayout":
        """
        Axiom 35: BackupRelays Where Hydronic.Backup is a gw.boiler.backup, its
        FailsafeRelayName and AquastatCtrlRelayName, and where it is a
        gw.element.backup, each name in its ElementRelayNames, SHALL equal the Name of
        an ShNode in ShNodes whose ActorClass is "Relay".
        """
        backup = self.hydronic.backup
        if backup is None:
            return self
        if backup.type_name == "gw.boiler.backup":
            names = [backup.failsafe_relay_name, backup.aquastat_ctrl_relay_name]
        else:
            names = list(backup.element_relay_names)
        relays = {
            n.name for n in (self.sh_nodes or []) if str(n.actor_class) == "Relay"
        }
        for name in names:
            if name not in relays:
                raise ValueError(
                    f"Axiom 35 (BackupRelays) failed: the backup names {name!r}, "
                    "which is not an ShNode with ActorClass Relay."
                )
        return self

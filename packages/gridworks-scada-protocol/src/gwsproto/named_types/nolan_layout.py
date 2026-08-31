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
    def check_axiom_3(self) -> "NolanLayout":
        """Axiom 3: RequiredRelays.

        a. ShNodes SHALL include nodes named "iso-valve-relay",
        "secondary-pump-relay", "hp-scada-ops-relay", "charge-valve-relay",
        "store-pump-relay", "buffer-top-elt-relay", "buffer-bottom-elt-relay",
        "store-top-elt-relay", and "store-bottom-elt-relay", each with
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
                    f"Axiom 3 (RequiredRelays) failed: no ShNode named "
                    f"{node_name} ({role})."
                )
            if actor_class != ActorClass.Relay:
                raise ValueError(
                    f"Axiom 3 (RequiredRelays) failed: {node_name} "
                    f"({role}) has ActorClass {actor_class}, not Relay."
                )

        for required in (
            "iso-valve-relay",
            "charge-valve-relay",
            "store-pump-relay",
            "buffer-top-elt-relay",
            "buffer-bottom-elt-relay",
            "store-top-elt-relay",
            "store-bottom-elt-relay",
            "secondary-pump-relay",
            "hp-scada-ops-relay",
        ):
            relay_or_raise(required, "plant relay")
        circuits = self.Hydronic.ZoneCallCircuits or []
        if not circuits:
            raise ValueError(
                "Axiom 3 (RequiredRelays) failed: Hydronic.ZoneCallCircuits is empty."
            )
        for circuit in circuits:
            relay_or_raise(circuit.FailsafeRelayNode, "circuit failsafe relay")
            relay_or_raise(circuit.OpsRelayNode, "circuit ops relay")
        return self

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
    def check_axiom_4(self) -> "NolanLayout":
        """Axiom 4: RequiredActors.

        ShNodes SHALL include nodes with these Name / ActorClass pairs: "s"
        PrimaryScada, "s2" SecondaryScada, "lc" LocalControl, "la" LeafAlly,
        "pico-cycler" PicoCycler, "derived-generator" DerivedGenerator, and
        "power-meter" PowerMeter.
        """
        actor_class_by_name = {n.Name: n.ActorClass for n in self.ShNodes}
        for name, actor_class in (
            ("s", ActorClass.PrimaryScada),
            ("s2", ActorClass.SecondaryScada),
            ("lc", ActorClass.LocalControl),
            ("la", ActorClass.LeafAlly),
            ("pico-cycler", ActorClass.PicoCycler),
            ("derived-generator", ActorClass.DerivedGenerator),
            ("power-meter", ActorClass.PowerMeter),
        ):
            got = actor_class_by_name.get(name)
            if got != actor_class:
                raise ValueError(
                    f"Axiom 4 (RequiredActors) failed: expected ShNode {name!r} "
                    f"with ActorClass {actor_class}, got {got!r}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_5(self) -> "NolanLayout":
        """Axiom 5: RequiredCommandNodes.

        ShNodes SHALL include nodes named "admin", "auto", "n", "ltn",
        "hp-odu", and "hp-ctrl-box", each with ActorClass "NoActor". The
        effective handle (Handle if present, otherwise Name) of "admin" SHALL
        be "admin", of "auto" SHALL be "auto", and of "n" SHALL be
        "auto.lc.n".
        """
        nodes = {n.Name: n for n in self.ShNodes}
        for name, handle in (
            ("admin", "admin"),
            ("auto", "auto"),
            ("n", "auto.lc.n"),
            ("ltn", None),
            ("hp-odu", None),
            ("hp-ctrl-box", None),
        ):
            node = nodes.get(name)
            if node is None or node.ActorClass != ActorClass.NoActor:
                raise ValueError(
                    f"Axiom 5 (RequiredCommandNodes) failed: expected ShNode "
                    f"{name!r} with ActorClass NoActor."
                )
            if handle is not None:
                effective = node.Handle if node.Handle is not None else node.Name
                if effective != handle:
                    raise ValueError(
                        f"Axiom 5 (RequiredCommandNodes) failed: {name!r} "
                        f"effective handle is {effective!r}, expected {handle!r}."
                    )
        return self

    @model_validator(mode="after")
    def check_axiom_6(self) -> "NolanLayout":
        """Axiom 6: RequiredBoardActors.

        ShNodes SHALL include exactly one node with ActorClass "I2cBus",
        exactly one with ActorClass "I2cThermistorReader", and exactly one
        with ActorClass "I2cDacWriter".
        """
        for actor_class in (
            ActorClass.I2cBus,
            ActorClass.I2cThermistorReader,
            ActorClass.I2cDacWriter,
        ):
            count = sum(1 for n in self.ShNodes if n.ActorClass == actor_class)
            if count != 1:
                raise ValueError(
                    f"Axiom 6 (RequiredBoardActors) failed: expected exactly "
                    f"one ShNode with ActorClass {actor_class}, found {count}."
                )
        return self

    @model_validator(mode="after")
    def check_axiom_7(self) -> "NolanLayout":
        """Axiom 7: RequiredSensing.

        For each required sensing name: a channel with that Name SHALL exist
        in DataChannels or in DerivedChannels. (Kind-agnostic by design: a
        name may migrate from raw DataChannel to same-name DerivedChannel —
        as tank temperatures did — without touching this contract.)
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
            )
            if name not in channel_names
        ]
        if missing:
            raise ValueError(
                f"Axiom 7 (RequiredSensing) failed: missing channels {missing}."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_8(self) -> "NolanLayout":
        """Axiom 8: SingleStoreTank.

        Hydronic.TotalStoreTanks SHALL equal 1 — the Nolan plant carries
        exactly one store tank.
        """
        if self.Hydronic.TotalStoreTanks != 1:
            raise ValueError(
                f"Axiom 8 (SingleStoreTank) failed: TotalStoreTanks is "
                f"{self.Hydronic.TotalStoreTanks}, expected 1."
            )
        return self

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from gwsproto.enums import ActorClass
from gwsproto.named_types.ads111x_based_device_type_gt import Ads111xBasedDeviceTypeGt
from gwsproto.named_types.electric_meter_device_type_gt import ElectricMeterDeviceTypeGt
from gwsproto.named_types.scada_device_type_gt import ScadaDeviceTypeGt
from gwsproto.named_types.data_channel_gt import DataChannelGt
from gwsproto.named_types.g_node_gt import GNodeGt
from gwsproto.named_types.hydronic import Hydronic
from gwsproto.named_types.derived_channel_gt import DerivedChannelGt
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
from gwsproto.named_types.sim_pico_tank_module_component_gt import (
    SimPicoTankModuleComponentGt,
)
from gwsproto.named_types.spaceheat_node_gt import SpaceheatNodeGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt

# The component types a Nolan (gw108) layout may contain (mirrors the sema draft oneOf).
NolanComponent = (
    ElectricMeterComponentGt
    | GpioSensorComponentGt
    | GpioRelayComponentGt
    | I2cDacWriterComponentGt
    | I2cMultichannelDtRelayComponentGt
    | I2cRelayComponentGt
    | I2cThermistorReaderComponentGt
    | PicoBtuMeterComponentGt
    | PicoTankModuleComponentGt
    | ScadaBoardComponentGt
    | SimPicoTankModuleComponentGt
    | WebServerComponentGt
)

# The specialized device-type records a Nolan layout may carry (mirrors the sema oneOf).
NolanDeviceType = (
    Ads111xBasedDeviceTypeGt
    | ElectricMeterDeviceTypeGt
    | ScadaDeviceTypeGt
)


class NolanLayout(BaseModel):
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
        """Axiom 3: LocalControlPlant.

        a. ShNodes SHALL include nodes named "iso-valve-relay",
        "secondary-pump-relay", and "hp-scada-ops-relay", each with
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
                    f"Axiom 3 (LocalControlPlant) failed: no ShNode named "
                    f"{node_name} ({role})."
                )
            if actor_class != ActorClass.Relay:
                raise ValueError(
                    f"Axiom 3 (LocalControlPlant) failed: {node_name} "
                    f"({role}) has ActorClass {actor_class}, not Relay."
                )

        for required in (
            "iso-valve-relay",
            "secondary-pump-relay",
            "hp-scada-ops-relay",
        ):
            relay_or_raise(required, "plant relay")
        circuits = self.Hydronic.ZoneCallCircuits or []
        if not circuits:
            raise ValueError(
                "Axiom 3 (LocalControlPlant) failed: Hydronic.ZoneCallCircuits is empty."
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

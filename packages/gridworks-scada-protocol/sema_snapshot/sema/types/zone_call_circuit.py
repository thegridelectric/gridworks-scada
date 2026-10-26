from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ZoneEmitterType
from sema_snapshot.sema.enums import ZoneSetpointSource
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.types.zone_thermostat import ZoneThermostat


class ZoneCallCircuit(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.zone.call.circuit/000"""

    circuit_position: PositiveInt
    name: SpaceheatName
    serves_zone: SpaceheatName
    emitter_type: ZoneEmitterType
    can_cool: bool
    setpoint_source: ZoneSetpointSource
    thermostat: ZoneThermostat
    whitewire_channel_name: SpaceheatName
    setpoint_channel_name: SpaceheatName | None = None
    temp_channel_name: SpaceheatName | None = None
    floor_temp_channel_name: SpaceheatName | None = None
    failsafe_relay_node: SpaceheatName
    ops_relay_node: SpaceheatName
    type_name: Literal["gw1.zone.call.circuit"] = "gw1.zone.call.circuit"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ZoneCallCircuit":
        """
        Axiom 1: OnlyFanCoilsCool If EmitterType is not FanCoil, CanCool SHALL be false.
        """
        # String comparison: the enum class name differs under a snapshot's
        # local names.
        if str(self.emitter_type) != "FanCoil" and self.can_cool:
            raise ValueError(
                f"Axiom 1 (OnlyFanCoilsCool) failed: EmitterType is "
                f"{self.emitter_type}, so CanCool SHALL be false."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "ZoneCallCircuit":
        """
        Axiom 2: ReadSetpointNeedsCommsStat If SetpointSource is FromThermostat,
        Thermostat.Kind SHALL NOT be MechanicalDial.
        """
        # String comparison, not an enum import: ThermostatKind is not a field
        # enum of this type, and an absolute sema.runtime import would break
        # inside a restricted snapshot package.
        if (
            self.setpoint_source == ZoneSetpointSource.FromThermostat
            and self.thermostat.kind == "MechanicalDial"
        ):
            raise ValueError(
                "Axiom 2 (ReadSetpointNeedsCommsStat) failed: SetpointSource is "
                "FromThermostat, so Thermostat.Kind SHALL NOT be MechanicalDial."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_3(self) -> "ZoneCallCircuit":
        """
        Axiom 3: SetpointNeedsTemp If SetpointChannelName is present, TempChannelName
        SHALL be present.
        """
        if self.setpoint_channel_name and not self.temp_channel_name:
            raise ValueError(
                "Axiom 3 (SetpointNeedsTemp) failed: the circuit carries "
                f"SetpointChannelName {self.setpoint_channel_name!r}, so it SHALL "
                "carry TempChannelName."
            )
        return self

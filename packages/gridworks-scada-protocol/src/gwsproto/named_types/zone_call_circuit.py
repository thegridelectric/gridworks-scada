from typing import Literal

from pydantic import BaseModel, PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    ThermostatKind,
    ZoneActuatorKind,
    ZoneCircuitRole,
    ZoneSetpointSource,
)
from gwsproto.named_types.zone_thermostat import ZoneThermostat
from gwsproto.property_format import SpaceheatName


class ZoneCallCircuit(BaseModel):
    """Sema: https://schemas.electricity.works/types/gw1.zone.call.circuit/000"""

    CircuitPosition: PositiveInt
    ServesZone: SpaceheatName
    ActuatorKind: ZoneActuatorKind
    Role: ZoneCircuitRole
    CanCool: bool
    SetpointSource: ZoneSetpointSource
    Thermostat: ZoneThermostat
    WhitewireChannelName: SpaceheatName
    FailsafeRelayNode: SpaceheatName
    OpsRelayNode: SpaceheatName
    TypeName: Literal["gw1.zone.call.circuit"] = "gw1.zone.call.circuit"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: FloorLoopsCannotCool. If ActuatorKind is FloorLoop, CanCool
        SHALL be false.
        """
        if self.ActuatorKind == ZoneActuatorKind.FloorLoop and self.CanCool:
            raise ValueError(
                "Axiom 1 (FloorLoopsCannotCool) failed: ActuatorKind is "
                "FloorLoop but CanCool is true."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ReadSetpointNeedsCommsStat. If SetpointSource is
        FromThermostat, Thermostat.Kind SHALL NOT be MechanicalDial.
        """
        if (
            self.SetpointSource == ZoneSetpointSource.FromThermostat
            and self.Thermostat.Kind == ThermostatKind.MechanicalDial
        ):
            raise ValueError(
                "Axiom 2 (ReadSetpointNeedsCommsStat) failed: SetpointSource "
                "is FromThermostat but Thermostat.Kind is MechanicalDial."
            )
        return self

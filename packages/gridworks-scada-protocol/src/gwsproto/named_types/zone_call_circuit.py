from typing import Literal

from pydantic import PositiveInt, model_validator
from typing_extensions import Self

from gwsproto.enums import (
    GwZoneEmitterType,
    ThermostatKind,
    ZoneSetpointSource,
)
from gwsproto.named_types.zone_thermostat import ZoneThermostat
from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ZoneCallCircuit(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw1.zone.call.circuit/000"""

    CircuitPosition: PositiveInt
    ServesZone: SpaceheatName
    EmitterType: GwZoneEmitterType
    CanCool: bool
    SetpointSource: ZoneSetpointSource
    Thermostat: ZoneThermostat
    WhitewireChannelName: SpaceheatName
    FloorTempChannelName: SpaceheatName | None = None
    FailsafeRelayNode: SpaceheatName
    OpsRelayNode: SpaceheatName
    TypeName: Literal["gw1.zone.call.circuit"] = "gw1.zone.call.circuit"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: OnlyFanCoilsCool. If EmitterType is not FanCoil, CanCool
        SHALL be false.
        """
        if self.EmitterType != GwZoneEmitterType.FanCoil and self.CanCool:
            raise ValueError(
                f"Axiom 1 (OnlyFanCoilsCool) failed: EmitterType is "
                f"{self.EmitterType}, so CanCool SHALL be false."
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

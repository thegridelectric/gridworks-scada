from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ThermostatKind
from sema_snapshot.sema.property_format import UUID4Str


class ZoneThermostat(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.zone.thermostat/000"""

    kind: ThermostatKind
    component_id: UUID4Str | None = None
    type_name: Literal["gw1.zone.thermostat"] = "gw1.zone.thermostat"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "ZoneThermostat":
        """
        Axiom 1: NoComponentOnDumbStat
        If Kind is MechanicalDial, ComponentId SHALL be absent.
        """
        if self.kind == ThermostatKind.MechanicalDial and self.component_id is not None:
            raise ValueError(
                "Axiom 1 (NoComponentOnDumbStat) failed: Kind is MechanicalDial, "
                f"so ComponentId SHALL be absent; got {self.component_id}."
            )
        return self

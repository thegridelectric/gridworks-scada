from typing import Literal, Optional

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.enums import ThermostatKind
from gwsproto.property_format import UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class ZoneThermostat(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw1.zone.thermostat/000"""

    Kind: ThermostatKind
    ComponentId: Optional[UUID4Str] = None
    TypeName: Literal["gw1.zone.thermostat"] = "gw1.zone.thermostat"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: NoComponentOnDumbStat. If Kind is MechanicalDial, ComponentId
        SHALL be absent.
        """
        if self.Kind == ThermostatKind.MechanicalDial and self.ComponentId is not None:
            raise ValueError(
                "Axiom 1 (NoComponentOnDumbStat) failed: Kind is MechanicalDial "
                "but ComponentId is present."
            )
        return self

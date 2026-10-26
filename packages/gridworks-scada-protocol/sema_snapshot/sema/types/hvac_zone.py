from typing import Literal
from pydantic import StrictFloat
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import SpaceheatName


class HvacZone(SemaType):
    """Sema: https://schemas.electricity.works/types/gw1.hvac.zone/000"""

    name: SpaceheatName
    critical: bool
    kwh_per_deg_f: StrictFloat
    primary_circuit_position: PositiveInt
    type_name: Literal["gw1.hvac.zone"] = "gw1.hvac.zone"
    version: Literal["000"] = "000"

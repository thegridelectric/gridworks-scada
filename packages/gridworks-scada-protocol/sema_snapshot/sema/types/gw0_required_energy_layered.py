from typing import Literal
from sema_snapshot.sema.base import SemaType


class Gw0RequiredEnergyLayered(SemaType):
    """Sema: https://schemas.electricity.works/types/gw0.required.energy.layered/000"""

    type_name: Literal["gw0.required.energy.layered"] = "gw0.required.energy.layered"
    version: Literal["000"] = "000"

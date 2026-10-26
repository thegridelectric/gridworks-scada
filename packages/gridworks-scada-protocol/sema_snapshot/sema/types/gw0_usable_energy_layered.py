from typing import Literal
from sema_snapshot.sema.base import SemaType


class Gw0UsableEnergyLayered(SemaType):
    """Sema: https://schemas.electricity.works/types/gw0.usable.energy.layered/000"""

    type_name: Literal["gw0.usable.energy.layered"] = "gw0.usable.energy.layered"
    version: Literal["000"] = "000"

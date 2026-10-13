from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType


class PowerWatts(SemaType):
    """Sema: https://schemas.electricity.works/types/power.watts/000"""

    watts: StrictInt
    type_name: Literal["power.watts"] = "power.watts"
    version: Literal["000"] = "000"

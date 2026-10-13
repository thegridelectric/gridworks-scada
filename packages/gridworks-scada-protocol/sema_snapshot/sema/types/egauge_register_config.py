from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType


class EgaugeRegisterConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/egauge.register.config/000"""

    address: StrictInt
    name: str
    description: str
    type: str
    denominator: StrictInt
    unit: str
    type_name: Literal["egauge.register.config"] = "egauge.register.config"
    version: Literal["000"] = "000"

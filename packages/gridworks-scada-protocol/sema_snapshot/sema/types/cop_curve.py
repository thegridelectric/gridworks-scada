from typing import Literal
from pydantic import StrictFloat
from sema_snapshot.sema.base import SemaType


class CopCurve(SemaType):
    """Sema: https://schemas.electricity.works/types/cop.curve/000"""

    intercept: StrictFloat
    oat_coeff: StrictFloat
    lwt_coeff: StrictFloat
    min: StrictFloat
    min_oat_f: StrictFloat
    type_name: Literal["cop.curve"] = "cop.curve"
    version: Literal["000"] = "000"

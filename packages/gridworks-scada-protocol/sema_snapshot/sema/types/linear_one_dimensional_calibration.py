from typing import Literal
from pydantic import StrictFloat, StrictInt
from sema_snapshot.sema.base import SemaType


class LinearOneDimensionalCalibration(SemaType):
    """Sema: https://schemas.electricity.works/types/linear.one.dimensional.calibration/000"""

    m: StrictFloat
    b: StrictInt
    type_name: Literal["linear.one.dimensional.calibration"] = (
        "linear.one.dimensional.calibration"
    )
    version: Literal["000"] = "000"

"""Type async.btu.data, version 000"""

from typing import Literal

from pydantic import BaseModel, StrictInt

from gwproto.enums import TelemetryName
from gwproto.property_format import (
    SpaceheatName,
)


class AsyncBtuData(BaseModel):
    HwUid: str
    AboutNodeNameList: list[SpaceheatName]
    MeasurementList: list[StrictInt]
    UnitList: list[TelemetryName]
    TypeName: Literal["async.btu.data"] = "async.btu.data"
    Version: Literal["000"] = "000"

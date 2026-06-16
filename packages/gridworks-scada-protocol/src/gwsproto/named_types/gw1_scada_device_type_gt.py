from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt


class Gw1ScadaDeviceTypeGt(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw1.scada.device.type.gt/000

    The specialized device-type record for a GridWorks SCADA board category.
    Minimal stub (carries board-level identity); hand-ported from the gwta snapshot.
    """

    DeviceType: str
    DisplayName: Optional[str] = None
    MinPollPeriodMs: Optional[PositiveInt] = None
    TypeName: Literal["gw1.scada.device.type.gt"] = "gw1.scada.device.type.gt"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

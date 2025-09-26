"""Type pico.comms.params, version 000"""

from typing import Literal


from pydantic import BaseModel


class PicoCommsParams(BaseModel):
    HwUid: str
    BaseUrl: str
    BackupUrl: str
    TypeName: Literal["pico.comms.params"] = "pico.comms.params"
    Version: str = "000"

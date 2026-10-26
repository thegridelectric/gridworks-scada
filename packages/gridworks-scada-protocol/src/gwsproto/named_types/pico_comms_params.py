"""Type pico.comms.params, version 000"""

from typing import Literal

from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType



class PicoCommsParams(GwsprotoSemaType):
    HwUid: str
    BaseUrl: str
    BackupUrl: str
    TypeName: Literal["pico.comms.params"] = "pico.comms.params"
    Version: str = "000"

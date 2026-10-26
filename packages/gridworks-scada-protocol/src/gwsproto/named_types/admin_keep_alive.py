
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal, Optional



class AdminKeepAlive(GwsprotoSemaType):
    AdminTimeoutSeconds: Optional[int] = None
    TypeName: Literal["admin.keep.alive"] = "admin.keep.alive"
    Version: Literal["000"] = "000"

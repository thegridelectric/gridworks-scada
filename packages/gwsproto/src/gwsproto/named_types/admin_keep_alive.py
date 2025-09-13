"""Type admin.keep.alive, version 000"""

from typing import Literal, Optional

from pydantic import BaseModel


class AdminKeepAlive(BaseModel):
    AdminTimeoutSeconds: Optional[int] = None
    TypeName: Literal["admin.keep.alive"] = "admin.keep.alive"
    Version: Literal["000"] = "000"

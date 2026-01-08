from typing import Literal

from pydantic import BaseModel


class AdminReleaseControl(BaseModel):
    TypeName: Literal["admin.release.control"] = "admin.release.control"
    Version: Literal["000"] = "000"

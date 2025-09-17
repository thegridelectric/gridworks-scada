"""Type admin.release.control, version 000"""

from typing import Literal

from pydantic import BaseModel


class AdminReleaseControl(BaseModel):
    """ """

    TypeName: Literal["admin.release.control"] = "admin.release.control"
    Version: str = "000"

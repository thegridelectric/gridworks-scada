from typing import Literal

from pydantic import BaseModel


class PowerWatts(BaseModel):
    """ASL: https://schemas.electricity.works/types/power.watts/000"""

    Watts: int
    TypeName: Literal["power.watts"] = "power.watts"
    Version: str = "000"

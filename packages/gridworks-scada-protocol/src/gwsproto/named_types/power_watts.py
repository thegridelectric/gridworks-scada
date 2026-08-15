
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class PowerWatts(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/power.watts/000"""

    Watts: int
    TypeName: Literal["power.watts"] = "power.watts"
    Version: str = "000"


from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from typing import Literal



class UsableEnergyLayered(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw0.usable.energy.layered/000
    
    Executable specification for computing usable thermal energy
    using a layered storage model.

    Version 000 assumes:
    - Ideal stratification within each layer
    - No thermal losses
    - Sequential discharge constrained by forecast-derived RWT
    - Active storage determined at runtime by SeasonalStorageMode
    """
    
    TypeName: Literal["gw0.usable.energy.layered"] = "gw0.usable.energy.layered"
    Version: Literal["000"] = "000"
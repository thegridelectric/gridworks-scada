from typing import Literal

from pydantic import BaseModel

class UsableEnergyLayered(BaseModel):
    """ASL: https://schemas.electricity.works/types/gw0.usable.energy.layered/000
    
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
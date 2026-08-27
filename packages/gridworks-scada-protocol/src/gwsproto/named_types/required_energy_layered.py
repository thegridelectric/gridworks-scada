from typing import Literal

from pydantic import BaseModel

class RequiredEnergyLayered(BaseModel):
    """ASL: https://schemas.electricity.works/types/gw0.required.energy.layered/000
    
    Executable specification for computing required thermal energy
    using a layered storage model.

    Version 000 computes the minimum thermal energy that must be
    available in storage to meet upcoming on-peak heating demand.

    The algorithm:
    - Uses a weather-driven heating forecast to estimate future load
    - Simulates layered discharge of active storage tanks or buffer
    - Assumes ideal stratification and no thermal losses
    - Determines required energy as the amount needed to survive
      the next on-peak period(s) under the current SeasonalStorageMode

    Active storage (buffer-only vs all tanks) is determined at runtime
    from settings, not from this specification.
    """
    
    TypeName: Literal["gw0.required.energy.layered"] = "gw0.required.energy.layered"
    Version: Literal["000"] = "000"
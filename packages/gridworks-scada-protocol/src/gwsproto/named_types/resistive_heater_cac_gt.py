from typing import Literal

from gwsproto.named_types import ComponentAttributeClassGt


class ResistiveHeaterCacGt(ComponentAttributeClassGt):
    NameplateMaxPowerW: int
    RatedVoltageV: int
    TypeName: Literal["resistive.heater.cac.gt"] = "resistive.heater.cac.gt"

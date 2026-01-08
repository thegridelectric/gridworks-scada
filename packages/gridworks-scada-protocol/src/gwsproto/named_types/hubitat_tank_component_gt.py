from typing import Literal

from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.named_types.hubitat_tank_gt import HubitatTankSettingsGt


class HubitatTankComponentGt(ComponentGt):
    Tank: HubitatTankSettingsGt
    TypeName: Literal["hubitat.tank.component.gt"] = "hubitat.tank.component.gt"

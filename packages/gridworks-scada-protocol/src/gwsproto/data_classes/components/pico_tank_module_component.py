from typing import Any
"""PicoTankModuleComponent definition"""

from gwsproto.data_classes.components.component import DeviceComponent
from gwsproto.named_types import PicoTankModuleComponentGt


class PicoTankModuleComponent(
    DeviceComponent[PicoTankModuleComponentGt, Any]
): ...

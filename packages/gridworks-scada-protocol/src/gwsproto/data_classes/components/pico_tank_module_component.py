from typing import Any
"""PicoTankModuleComponent definition"""

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import PicoTankModuleComponentGt


class PicoTankModuleComponent(
    Component[PicoTankModuleComponentGt, Any]
): ...

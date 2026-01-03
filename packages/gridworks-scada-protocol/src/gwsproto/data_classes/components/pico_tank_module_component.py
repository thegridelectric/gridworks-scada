"""PicoTankModuleComponent definition"""

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import ComponentAttributeClassGt, PicoTankModuleComponentGt


class PicoTankModuleComponent(
    Component[PicoTankModuleComponentGt, ComponentAttributeClassGt]
): ...

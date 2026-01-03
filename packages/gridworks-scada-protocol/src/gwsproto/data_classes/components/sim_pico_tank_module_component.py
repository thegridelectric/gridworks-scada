from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import ComponentAttributeClassGt
from gwsproto.named_types import SimPicoTankModuleComponentGt

class SimPicoTankModuleComponent(
    Component[SimPicoTankModuleComponentGt, ComponentAttributeClassGt]
): ...

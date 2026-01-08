from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import (
    ComponentAttributeClassGt,
    I2cMultichannelDtRelayComponentGt,
)


class I2cMultichannelDtRelayComponent(
    Component[I2cMultichannelDtRelayComponentGt, ComponentAttributeClassGt]
): ...

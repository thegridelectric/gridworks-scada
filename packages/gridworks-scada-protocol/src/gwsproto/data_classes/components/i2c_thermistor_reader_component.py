from gwsproto.data_classes.components.component import Component
from gwsproto.named_types import (
    ComponentAttributeClassGt,
    I2cThermistorReaderComponentGt,
)


class I2cThermistorReaderComponent(
    Component[I2cThermistorReaderComponentGt, ComponentAttributeClassGt]
): ...

"""PicoBtuMeterComponent definition"""

from gwproto.data_classes.components.component import Component
from gwproto.named_types import ComponentAttributeClassGt #, PicoBtuMeterComponentGt
from gwsproto.named_types import PicoBtuMeterComponentGt


class PicoBtuMeterComponent(
    Component[PicoBtuMeterComponentGt, ComponentAttributeClassGt]
): ...

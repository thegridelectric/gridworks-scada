from gwsproto.data_classes.components.component import DeviceComponent
from gwsproto.named_types import Ads111xBasedDeviceTypeGt, Ads111xBasedComponentGt


class Ads111xBasedComponent(
    DeviceComponent[Ads111xBasedComponentGt, Ads111xBasedDeviceTypeGt]
): ...

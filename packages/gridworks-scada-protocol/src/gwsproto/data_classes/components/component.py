from typing import Any, Generic, Optional, TypeVar

from gwsproto.named_types import ComponentGt

ComponentT = TypeVar("ComponentT", bound=ComponentGt)
# The specialized device-type record (a *.device.type.gt). Records are flat per family,
# so the bound is open (Any) rather than a shared base class.
DeviceTypeT = TypeVar("DeviceTypeT")


class Component(Generic[ComponentT, DeviceTypeT]):
    # device_type is the specialized device-type record, joined by the shared DeviceType.
    # It is OPTIONAL: a device category with no category-level data carries no record (None).
    gt: ComponentT
    device_type: Optional[DeviceTypeT]

    def __init__(self, gt: ComponentT, device_type: Optional[DeviceTypeT] = None) -> None:
        self.gt = gt
        self.device_type = device_type

    def __repr__(self) -> str:
        return f"<{self.gt.DisplayName}>  ({self.gt.DeviceType})"


class ComponentOnly(Component[ComponentGt, Any]): ...

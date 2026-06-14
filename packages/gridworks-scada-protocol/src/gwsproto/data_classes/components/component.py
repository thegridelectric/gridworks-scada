from typing import Generic, Optional, TypeVar

from gwsproto.named_types import ComponentAttributeClassGt, ComponentGt

ComponentT = TypeVar("ComponentT", bound=ComponentGt)
CacT = TypeVar("CacT", bound=ComponentAttributeClassGt)


class Component(Generic[ComponentT, CacT]):
    # cac is the specialized device-type record, joined by the shared DeviceType. It is
    # OPTIONAL: a device category with no category-level data carries no record (None).
    gt: ComponentT
    cac: Optional[CacT]

    def __init__(self, gt: ComponentT, cac: Optional[CacT] = None) -> None:
        self.gt = gt
        self.cac = cac

    def __repr__(self) -> str:
        return f"<{self.gt.DisplayName}>  ({self.gt.DeviceType})"


class ComponentOnly(Component[ComponentGt, ComponentAttributeClassGt]): ...

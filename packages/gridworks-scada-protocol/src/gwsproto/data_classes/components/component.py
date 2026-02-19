from typing import Generic, TypeVar

from gwsproto.named_types import ComponentAttributeClassGt, ComponentGt

ComponentT = TypeVar("ComponentT", bound=ComponentGt)
CacT = TypeVar("CacT", bound=ComponentAttributeClassGt)


class Component(Generic[ComponentT, CacT]):
    gt: ComponentT
    cac: CacT

    def __init__(self, gt: ComponentT, cac: CacT) -> None:
        self.gt = gt
        self.cac = cac

    def __repr__(self) -> str:
        return f"<{self.gt.DisplayName}>  ({self.cac.MakeModel})"


class ComponentOnly(Component[ComponentGt, ComponentAttributeClassGt]): ...

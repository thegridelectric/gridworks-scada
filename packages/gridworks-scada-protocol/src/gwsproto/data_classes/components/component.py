from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from gwsproto.errors import DcError
from gwsproto.type_helpers.component_base import (
    BoardResidentComponentBase,
    ComponentBase,
    DeviceComponentBase,
)

if TYPE_CHECKING:
    from gwsproto.data_classes.components.scada_board_component import (
        ScadaBoardComponent,
    )

ComponentT = TypeVar("ComponentT", bound=ComponentBase)
DeviceComponentT = TypeVar("DeviceComponentT", bound=DeviceComponentBase)
BoardResidentComponentT = TypeVar(
    "BoardResidentComponentT", bound=BoardResidentComponentBase
)
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
        return f"<{self.gt.DisplayName}>"


class ComponentOnly(Component[ComponentBase, Any]):
    """The fallback dc: get_data_class_class resolves here when a component
    gt has no specialized data class of its own."""


# The two dc families mirror the gt families in type_helpers.component_base:
# DeviceComponentBase -> DeviceComponent, BoardResidentComponentBase ->
# BoardResidentComponent. The bounded TypeVars enforce the pairing
# statically; the __init__ guards enforce it at construction.


class DeviceComponent(Component[DeviceComponentT, DeviceTypeT]):
    """A component that is its own device: gt.DeviceType names the category
    and device_type is the joined specialized record (when the category
    carries one)."""

    def __init__(
        self, gt: DeviceComponentT, device_type: Optional[DeviceTypeT] = None
    ) -> None:
        if not isinstance(gt, DeviceComponentBase):
            raise DcError(
                f"{type(self).__name__} requires a DeviceComponentBase gt; "
                f"got {type(gt).__name__}"
            )
        super().__init__(gt, device_type)


class BoardResidentComponent(Component[BoardResidentComponentT, Any]):
    """A component resident on a scada board: gt.BoardComponentId anchors it,
    and the board's device-type record carries the physical facts.

    Constructed WITH its resolved board — load_components builds the boards
    first, and the layout's BoardResolution axiom guarantees each board
    exists — so board_component is never None."""

    board_component: "ScadaBoardComponent"

    def __init__(
        self,
        gt: BoardResidentComponentT,
        device_type: Optional[Any] = None,
        *,
        board_component: "ScadaBoardComponent",
    ) -> None:
        if not isinstance(gt, BoardResidentComponentBase):
            raise DcError(
                f"{type(self).__name__} requires a BoardResidentComponentBase gt; "
                f"got {type(gt).__name__}"
            )
        from gwsproto.data_classes.components.scada_board_component import (
            ScadaBoardComponent,
        )
        if not isinstance(board_component, ScadaBoardComponent):
            raise DcError(
                f"{type(self).__name__} requires a ScadaBoardComponent board; "
                f"got {type(board_component).__name__}"
            )
        super().__init__(gt, device_type)
        self.board_component = board_component

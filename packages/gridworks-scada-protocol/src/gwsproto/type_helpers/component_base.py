from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel

from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.property_format import UUID4Str


class ComponentBase(BaseModel):
    """The fields every Spaceheat component shares."""

    ComponentId: UUID4Str
    ConfigList: Sequence[CaptureTuning]
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None


class DeviceComponentBase(ComponentBase):
    """A component that is its own device (external, board-level, simulated,
    or abstract): DeviceType names its device category."""

    DeviceType: str


class BoardResidentComponentBase(ComponentBase):
    """A component resident on a scada board, anchored by BoardComponentId.
    No DeviceType: TypeName is the kind; the board component carries the
    board identity."""

    BoardComponentId: UUID4Str

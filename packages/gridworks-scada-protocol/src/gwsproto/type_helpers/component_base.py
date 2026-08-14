from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel

from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.property_format import UUID4Str


class ComponentBase(BaseModel):
    """The fields every Spaceheat component shares. ConfigList is NOT here:
    only components whose sema word declares it (per-channel identity/binding
    configs, not just capture tuning) carry it — see ConfigListMixin. Bare
    components' capture tuning lives on the operational-params artifact
    (CaptureTuningList), looked up at runtime via
    HardwareLayout.capture_tuning_by_channel."""

    ComponentId: UUID4Str
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None


class ConfigListMixin(BaseModel):
    """Mixin for components whose sema word declares ConfigList: per-channel
    identity/binding configs (relay wiring, DAC channel assignment, etc.),
    not merely capture tuning."""

    ConfigList: Sequence[CaptureTuning]


class DeviceComponentBase(ComponentBase):
    """A component that is its own device (external, board-level, simulated,
    or abstract): DeviceType names its device category."""

    DeviceType: str


class BoardResidentComponentBase(ComponentBase):
    """A component resident on a scada board, anchored by BoardComponentId.
    No DeviceType: TypeName is the kind; the board component carries the
    board identity."""

    BoardComponentId: UUID4Str

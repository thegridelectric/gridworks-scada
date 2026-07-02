from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel

from gwsproto.named_types.capture_tuning import CaptureTuning
from gwsproto.property_format import UUID4Str


class ComponentBase(BaseModel):
    ComponentId: UUID4Str
    DeviceType: str
    ConfigList: Sequence[CaptureTuning]
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None

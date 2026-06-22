from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel

from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.property_format import UUID4Str


class ComponentBase(BaseModel):
    ComponentId: UUID4Str
    DeviceType: str
    ConfigList: Sequence[ChannelConfig]
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None

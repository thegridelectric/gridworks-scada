from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel, field_validator

from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.property_format import UUID4Str


class ComponentGt(BaseModel):
    ComponentId: UUID4Str
    ComponentAttributeClassId: UUID4Str
    ConfigList: Sequence[ChannelConfig]
    DisplayName: Optional[str] = None
    HwUid: Optional[str] = None
    TypeName: str = "component.gt"
    Version: str = "001"

    @field_validator("ConfigList")
    @classmethod
    def check_config_list(cls, v: Sequence[ChannelConfig]) -> Sequence[ChannelConfig]:
        """
        Axiom 1: Channel Name uniqueness. Data Channel names are
        unique in the config list
        """
        # Implement Axiom(s)
        return v

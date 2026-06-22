from collections.abc import Sequence
from typing import Literal

from pydantic import field_validator

from gwsproto.named_types.channel_config import ChannelConfig
from gwsproto.type_helpers.component_base import ComponentBase
from gwproto.named_types.web_server_gt import WebServerGt


class WebServerComponentGt(ComponentBase):
    WebServer: WebServerGt
    TypeName: Literal["web.server.component.gt"] = "web.server.component.gt"
    Version: Literal["002"] = "002"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: Sequence[ChannelConfig]) -> Sequence[ChannelConfig]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

from typing import Literal

from pydantic import PositiveInt, field_validator

from gwsproto.type_helpers.component_base import ComponentBase
from gwsproto.named_types.relay_actor_config import RelayActorConfig



class Gw108GpioRelayComponentGt(ComponentBase):
    GpioPin: PositiveInt
    ConfigList: list[RelayActorConfig]
    TypeName: Literal["gw108.vdc.relay.component.gt"] = "gw108.vdc.relay.component.gt"
    Version: Literal["002"] = "002"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[RelayActorConfig]) -> list[RelayActorConfig]:
        """Axiom 1: Channel Name uniqueness. Data Channel names are unique in the ConfigList."""
        channel_names = [config.ChannelName for config in v]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
            raise ValueError(
                f"Axiom 1 violated! Channel names must be unique in the ConfigList; duplicates: {duplicates}"
            )
        return v

    @field_validator("ConfigList")
    @classmethod
    def exactly_one_relay(cls, v: list[RelayActorConfig]) -> list[RelayActorConfig]:
        if len(v) != 1:
            raise ValueError(
                "Gw108GpioRelayComponentGt must define exactly one RelayActorConfig"
            )
        return v

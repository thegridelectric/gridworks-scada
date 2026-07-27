from typing import Literal

from pydantic import ConfigDict, StrictInt, field_validator, model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwsproto.named_types.relay_actor_config import RelayActorConfig


class I2cMultichannelDtRelayComponentGt(DeviceComponentBase):
    I2cBus: SpaceheatName
    I2cAddressList: list[StrictInt]
    ConfigList: list[RelayActorConfig]
    TypeName: Literal["i2c.multichannel.dt.relay.component.gt"] = (
        "i2c.multichannel.dt.relay.component.gt"
    )
    Version: Literal["005"] = "005"

    model_config = ConfigDict(extra="allow", use_enum_values=True)

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

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: ActorIdxConsistency.
        There are no duplicates of ActorName or RelayIdx in the RelayConfigList
        """
        actor_names = [cfg.ActorName for cfg in self.ConfigList]
        if len(actor_names) != len(set(actor_names)):
            duplicates = sorted({name for name in actor_names if actor_names.count(name) > 1})
            raise ValueError(f"Duplicate ActorName(s) {duplicates}")

        relay_idxs = [cfg.RelayIdx for cfg in self.ConfigList]
        if len(relay_idxs) != len(set(relay_idxs)):
            duplicates = sorted({idx for idx in relay_idxs if relay_idxs.count(idx) > 1})
            raise ValueError(f"Duplicate RelayIdx(s) {duplicates}")
        return self

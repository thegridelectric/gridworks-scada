from typing import Literal
from pydantic import ConfigDict, StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.relay_actor_config import RelayActorConfig


class I2cMultichannelDtRelayComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.multichannel.dt.relay.component.gt/004"""

    component_id: UUID4Str
    device_type: PascalCase
    config_list: list[RelayActorConfig]
    display_name: str | None = None
    hw_uid: str | None = None
    i2c_bus: SpaceheatName
    i2c_address_list: list[StrictInt]
    type_name: Literal["i2c.multichannel.dt.relay.component.gt"] = (
        "i2c.multichannel.dt.relay.component.gt"
    )
    version: Literal["004"] = "004"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))

    @model_validator(mode="after")
    def check_axiom_1(self) -> "I2cMultichannelDtRelayComponentGt":
        """
        Axiom 1: ChannelNameUniqueness
        Channel names SHALL be unique across the ConfigList.
        """
        channel_names = [config.channel_name for config in self.config_list]
        if len(channel_names) != len(set(channel_names)):
            raise ValueError(
                "Axiom 1 (ChannelNameUniqueness) failed: channel names must be "
                "unique across the ConfigList."
            )
        return self

    @model_validator(mode="after")
    def check_axiom_2(self) -> "I2cMultichannelDtRelayComponentGt":
        """
        Axiom 2: ActorAndRelayIndexUniqueness
        ConfigList SHALL NOT contain duplicate ActorName values or duplicate RelayIdx
        values.
        """
        actor_names = [c.actor_name for c in self.config_list]
        relay_idxs = [c.relay_idx for c in self.config_list]
        if len(actor_names) != len(set(actor_names)):
            raise ValueError(
                "Axiom 2 (ActorAndRelayIndexUniqueness): ConfigList SHALL NOT "
                "contain duplicate ActorName values."
            )
        if len(relay_idxs) != len(set(relay_idxs)):
            raise ValueError(
                "Axiom 2 (ActorAndRelayIndexUniqueness): ConfigList SHALL NOT "
                "contain duplicate RelayIdx values."
            )
        return self

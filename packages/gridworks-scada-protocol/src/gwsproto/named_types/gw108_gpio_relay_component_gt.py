from typing import Literal

from pydantic import PositiveInt, field_validator

from gwsproto.named_types import ComponentGt
from gwsproto.named_types.relay_actor_config import RelayActorConfig



class Gw108GpioRelayComponentGt(ComponentGt):
    GpioPin: PositiveInt
    ConfigList: list[RelayActorConfig]
    TypeName: Literal["gw108.vdc.relay.component.gt"] = "gw108.vdc.relay.component.gt"
    Version: Literal["001"] = "001"

    @field_validator("ConfigList")
    @classmethod
    def exactly_one_relay(cls, v: list[RelayActorConfig]) -> list[RelayActorConfig]:
        if len(v) != 1:
            raise ValueError(
                "Gw108GpioRelayComponentGt must define exactly one RelayActorConfig"
            )
        return v

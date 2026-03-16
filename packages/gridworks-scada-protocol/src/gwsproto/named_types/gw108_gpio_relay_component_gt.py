from typing import Literal
from typing_extensions import Self

from pydantic import PositiveInt, field_validator,  model_validator

from gwsproto.named_types import ComponentGt
from gwsproto.named_types.relay_actor_config import RelayActorConfig



class Gw108GpioRelayComponentGt(ComponentGt):
    GpioPin: PositiveInt
    ConfigList: list[RelayActorConfig]
    TypeName: Literal["gw108.vdc.relay.component.gt"] = "gw108.vdc.relay.component.gt"
    Version: Literal["001"] = "001"

    @field_validator("ConfigList")
    @classmethod
    def check_axiom_1(cls, v: list[RelayActorConfig]) -> list[RelayActorConfig]:
        """Axiom 1: exactly one relay"""
        if len(v) != 1:
            raise ValueError(
                "Gw108GpioRelayComponentGt must define exactly one RelayActorConfig"
            )
        return v

    @model_validator(mode="after")
    def check_axiom_2(self) -> Self:
        """
        Axiom 2: GPIO pin matches RelayActorConfig RelayIdx
        """
        if self.GpioPin != self.ConfigList[0].RelayIdx:
            raise Exception(f"GPIO pin {self.GpioPin} must match "
                            f"relayActorConfig RelayIdx!")
        return self
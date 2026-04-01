from typing import Literal

from pydantic import ConfigDict, StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import SpaceheatName
from gwsproto.named_types.component_gt import ComponentGt
from gwsproto.named_types.relay_actor_config import RelayActorConfig


class I2cMultichannelDtRelayComponentGt(ComponentGt):
    I2cBus: SpaceheatName
    I2cAddressList: list[StrictInt]
    ConfigList: list[RelayActorConfig]
    TypeName: Literal["i2c.multichannel.dt.relay.component.gt"] = (
        "i2c.multichannel.dt.relay.component.gt"
    )
    Version: Literal["004"] = "004"

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: ActorIdxConsistency.
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

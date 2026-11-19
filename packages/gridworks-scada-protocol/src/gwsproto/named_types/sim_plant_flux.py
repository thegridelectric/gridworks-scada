from typing import Literal

from pydantic import StrictInt, model_validator
from typing_extensions import Self

from gwsproto.property_format import (
    SpaceheatName,
    UtcIso8601Millis,
    UTCMilliseconds,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SimPlantFlux(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/sim.plant.flux/000"""

    ChannelNameList: list[SpaceheatName]
    ValueList: list[StrictInt]
    ScadaReadTimeUnixMs: UTCMilliseconds
    ActualTimeUtc: UtcIso8601Millis
    TypeName: Literal["sim.plant.flux"] = "sim.plant.flux"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        if len(self.ChannelNameList) != len(self.ValueList):
            raise ValueError(
                "Axiom 1 (ListLengthConsistency) failed: "
                f"{len(self.ChannelNameList)} channel names, "
                f"{len(self.ValueList)} values"
            )
        return self

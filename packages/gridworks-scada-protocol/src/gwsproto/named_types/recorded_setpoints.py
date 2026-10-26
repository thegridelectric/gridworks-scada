from typing import List, Literal

from pydantic import model_validator
from typing_extensions import Self

from gwsproto.named_types.single_reading import SingleReading
from gwsproto.property_format import LeftRightDotStr
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class RecordedSetpoints(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.recorded.setpoints/000"""

    ScadaAlias: LeftRightDotStr
    SetpointList: List[SingleReading]
    TypeName: Literal["gw.recorded.setpoints"] = "gw.recorded.setpoints"
    Version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> Self:
        """
        Axiom 1: SetpointChannelUniqueness.
        ChannelName is unique across the SetpointList.
        """
        channel_names = [r.ChannelName for r in self.SetpointList]
        if len(channel_names) != len(set(channel_names)):
            duplicates = sorted(
                {n for n in channel_names if channel_names.count(n) > 1}
            )
            raise ValueError(
                "Axiom 1 (SetpointChannelUniqueness) failed: ChannelName must be "
                f"unique across SetpointList; duplicates: {duplicates}"
            )
        return self

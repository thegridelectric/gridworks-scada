from typing import Literal
from pydantic import model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.types.single_reading import SingleReading


class RecordedSetpoints(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.recorded.setpoints/000"""

    scada_alias: LeftRightDot
    setpoint_list: list[SingleReading]
    type_name: Literal["gw.recorded.setpoints"] = "gw.recorded.setpoints"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "RecordedSetpoints":
        """
        Axiom 1: SetpointChannelUniqueness
        ChannelName SHALL be unique across SetpointList.
        """
        channel_names = [reading.channel_name for reading in self.setpoint_list]
        duplicates = sorted({n for n in channel_names if channel_names.count(n) > 1})
        if duplicates:
            raise ValueError(
                "Axiom 1 (SetpointChannelUniqueness) failed: ChannelName is not "
                f"unique across SetpointList; duplicates: {duplicates}"
            )
        return self

from typing import Literal
from pydantic import StrictInt, model_validator
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds


class SyncedReadings(SemaType):
    """Sema: https://schemas.electricity.works/types/synced.readings/000"""

    channel_name_list: list[SpaceheatName]
    value_list: list[StrictInt]
    scada_read_time_unix_ms: UTCMilliseconds
    type_name: Literal["synced.readings"] = "synced.readings"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "SyncedReadings":
        """
        Axiom 1: ListLengthConsistency
        len(ChannelNameList) SHALL equal len(ValueList).
        """
        if len(self.channel_name_list) != len(self.value_list):
            raise ValueError(
                "Axiom 1 failed: channel_name_list and value_list must have the "
                f"same length (got {len(self.channel_name_list)} and "
                f"{len(self.value_list)})."
            )
        return self

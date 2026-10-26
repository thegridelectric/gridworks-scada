from typing import List, Literal

from gwsproto.named_types.single_machine_state import SingleMachineState
from gwsproto.named_types.single_reading import SingleReading
from gwsproto.property_format import (
    LeftRightDotStr,
    UTCMilliseconds,
    UUID4Str,
)
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class SnapshotSpaceheat(GwsprotoSemaType):
    """
    Snapshot.

    Collection of all the latest measurements (timestamped) captured by the SCADA for all of
    its data channels. Add LatestStateList
    """

    FromGNodeAlias: LeftRightDotStr
    FromGNodeInstanceId: UUID4Str
    SnapshotTimeUnixMs: UTCMilliseconds
    LatestReadingList: List[SingleReading]
    LatestStateList: List[SingleMachineState]
    TypeName: Literal["snapshot.spaceheat"] = "snapshot.spaceheat"
    Version: Literal["003"] = "003"

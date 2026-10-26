from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.single_machine_state import SingleMachineState
from sema_snapshot.sema.types.single_reading import SingleReading


class SnapshotSpaceheat(SemaType):
    """Sema: https://schemas.electricity.works/types/snapshot.spaceheat/003"""

    from_g_node_alias: LeftRightDot
    from_g_node_instance_id: UUID4Str
    snapshot_time_unix_ms: UTCMilliseconds
    latest_reading_list: list[SingleReading]
    latest_state_list: list[SingleMachineState]
    type_name: Literal["snapshot.spaceheat"] = "snapshot.spaceheat"
    version: Literal["003"] = "003"

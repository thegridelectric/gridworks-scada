from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import ScadaCmdRefusalReason
from sema_snapshot.sema.property_format import HandleName
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class DispatchNack(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.nack/000"""

    from_handle: HandleName
    to_handle: HandleName
    trigger_id: UUID4Str
    reason: ScadaCmdRefusalReason
    unix_time_ms: UTCMilliseconds
    type_name: Literal["gw.dispatch.nack"] = "gw.dispatch.nack"
    version: Literal["000"] = "000"

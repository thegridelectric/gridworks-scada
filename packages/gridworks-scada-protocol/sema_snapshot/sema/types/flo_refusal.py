from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import FloRefusalReason
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import NonEmptyString
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UTCSeconds


class FloRefusal(SemaType):
    """Sema: https://schemas.electricity.works/types/flo.refusal/000"""

    bidder_alias: LeftRightDot
    start_unix_s: UTCSeconds
    reason: FloRefusalReason
    detail: NonEmptyString | None = None
    created_ms: UTCMilliseconds
    type_name: Literal["flo.refusal"] = "flo.refusal"
    version: Literal["000"] = "000"

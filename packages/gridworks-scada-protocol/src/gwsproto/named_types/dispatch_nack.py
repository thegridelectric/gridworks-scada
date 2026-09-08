from typing import Literal

from gwsproto.enums import GwScadaCmdRefusalReason
from gwsproto.property_format import HandleName, UTCMilliseconds, UUID4Str
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class DispatchNack(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/gw.dispatch.nack/000"""

    FromHandle: HandleName
    ToHandle: HandleName
    TriggerId: UUID4Str
    Reason: GwScadaCmdRefusalReason
    UnixTimeMs: UTCMilliseconds
    TypeName: Literal["gw.dispatch.nack"] = "gw.dispatch.nack"
    Version: Literal["000"] = "000"


from typing import Literal, Optional

from gwsproto.enums import FloRefusalReason
from gwsproto.property_format import LeftRightDotStr, NonEmptyString, UTCMilliseconds, UTCSeconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class FloRefusal(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/flo.refusal/000"""

    BidderAlias: LeftRightDotStr
    StartUnixS: UTCSeconds
    Reason: FloRefusalReason
    Detail: Optional[NonEmptyString] = None
    CreatedMs: UTCMilliseconds
    TypeName: Literal["flo.refusal"] = "flo.refusal"
    Version: Literal["000"] = "000"

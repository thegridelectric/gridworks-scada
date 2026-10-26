from typing import Literal
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import DispatchRefusalReason
from sema_snapshot.sema.property_format import LeftRightDot
from sema_snapshot.sema.property_format import UTCMilliseconds
from sema_snapshot.sema.property_format import UUID4Str


class SlowContractRejection(SemaType):
    """Sema: https://schemas.electricity.works/types/slow.contract.rejection/000"""

    from_g_node_alias: LeftRightDot
    contract_id: UUID4Str
    reason: DispatchRefusalReason
    message_created_ms: UTCMilliseconds
    type_name: Literal["slow.contract.rejection"] = "slow.contract.rejection"
    version: Literal["000"] = "000"

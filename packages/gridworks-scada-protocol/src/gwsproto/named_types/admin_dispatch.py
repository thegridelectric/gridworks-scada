from typing import Literal

from pydantic import StrictInt

from gwsproto.named_types.fsm_event import FsmEvent
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class AdminDispatch(GwsprotoSemaType):
    DispatchTrigger: FsmEvent
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.dispatch"] = "admin.dispatch"
    Version: Literal["000"] = "000"

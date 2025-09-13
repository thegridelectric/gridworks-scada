"""Type admin.dispatch, version 000"""

from typing import Literal

from gwsproto.named_types.fsm_event import FsmEvent
from pydantic import BaseModel, StrictInt


class AdminDispatch(BaseModel):
    DispatchTrigger: FsmEvent
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.dispatch"] = "admin.dispatch"
    Version: Literal["000"] = "000"

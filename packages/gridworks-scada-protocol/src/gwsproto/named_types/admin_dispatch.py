from typing import Literal

from pydantic import BaseModel, StrictInt

from gwsproto.named_types.fsm_event import FsmEvent


class AdminDispatch(BaseModel):
    DispatchTrigger: FsmEvent
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.dispatch"] = "admin.dispatch"
    Version: Literal["000"] = "000"

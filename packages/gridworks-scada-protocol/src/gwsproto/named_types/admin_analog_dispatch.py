from typing import Literal
from pydantic import BaseModel, StrictInt

from gwsproto.named_types.analog_dispatch import AnalogDispatch


class AdminAnalogDispatch(BaseModel):
    Dispatch: AnalogDispatch
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.analog.dispatch"] = "admin.analog.dispatch"
    Version: Literal["000"] = "000"

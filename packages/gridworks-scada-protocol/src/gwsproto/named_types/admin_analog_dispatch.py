"""Type admin.dispatch, version 000"""

from typing import Literal

from gwproto.named_types import AnalogDispatch

from pydantic import BaseModel, StrictInt


class AdminAnalogDispatch(BaseModel):
    Dispatch: AnalogDispatch
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.analog.dispatch"] = "admin.analog.dispatch"
    Version: str = "000"

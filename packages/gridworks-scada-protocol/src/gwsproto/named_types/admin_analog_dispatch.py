from typing import Literal
from pydantic import StrictInt

from gwsproto.named_types.analog_dispatch import AnalogDispatch
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class AdminAnalogDispatch(GwsprotoSemaType):
    Dispatch: AnalogDispatch
    TimeoutSeconds: StrictInt
    TypeName: Literal["admin.analog.dispatch"] = "admin.analog.dispatch"
    Version: Literal["000"] = "000"

from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import SpaceheatName
from sema_snapshot.sema.property_format import UTCMilliseconds


class SingleReading(SemaType):
    """Sema: https://schemas.electricity.works/types/single.reading/000"""

    channel_name: SpaceheatName
    value: StrictInt
    scada_read_time_unix_ms: UTCMilliseconds
    type_name: Literal["single.reading"] = "single.reading"
    version: Literal["000"] = "000"

import time
from typing import Any, Literal

from gwsproto.enums import LogLevel
from gwsproto.property_format import LeftRightDotStr, SpaceheatName, UTCMilliseconds
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType


class Glitch(GwsprotoSemaType):
    """Sema: https://schemas.electricity.works/types/glitch/000"""

    FromGNodeAlias: LeftRightDotStr
    Node: SpaceheatName
    Type: LogLevel
    Summary: str
    Details: str
    CreatedMs: UTCMilliseconds
    TypeName: Literal["glitch"] = "glitch"
    Version: Literal["000"] = "000"

    def __init__(self, **data: Any) -> None:
        # Construction stamps the clock; decoding (model_validate and the
        # discriminated-union decoders) requires the field on the wire.
        data.setdefault("CreatedMs", int(time.time() * 1000))
        super().__init__(**data)

    # Pydantic routes validation through a custom __init__ unless it carries
    # this marker; with it, only direct construction runs the defaulting.
    __init__.__pydantic_base_init__ = True  # type: ignore[attr-defined]

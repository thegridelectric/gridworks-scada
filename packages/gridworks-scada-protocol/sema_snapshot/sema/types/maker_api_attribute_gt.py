from typing import Literal
from pydantic import StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.enums import SpaceheatUnit
from sema_snapshot.sema.enums import TelemetryName
from sema_snapshot.sema.property_format import SpaceheatName


class MakerApiAttributeGt(SemaType):
    """Sema: https://schemas.electricity.works/types/maker.api.attribute.gt/001"""

    attribute_name: str
    channel_name: SpaceheatName
    node_name: SpaceheatName
    telemetry_name: TelemetryName
    unit: SpaceheatUnit
    exponent: StrictInt
    interpret_as_number: bool
    web_poll_enabled: bool
    web_listen_enabled: bool
    report_missing: bool
    report_parse_error: bool
    type_name: Literal["maker.api.attribute.gt"] = "maker.api.attribute.gt"
    version: Literal["001"] = "001"

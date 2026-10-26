from typing import Literal

from pydantic import ConfigDict

from gwsproto.enums import TelemetryName, SpaceheatUnit
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from gwproto.utils import snake_to_camel


class MakerAPIAttributeGt(GwsprotoSemaType):
    attribute_name: str
    channel_name: str
    node_name: str
    telemetry_name: TelemetryName
    unit: SpaceheatUnit
    exponent: int
    interpret_as_number: bool
    web_poll_enabled: bool
    web_listen_enabled: bool
    report_missing: bool
    report_parse_error: bool
    type_name: Literal["maker.api.attribute.gt"] = "maker.api.attribute.gt"
    version: Literal["001"] = "001"

    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True,
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )


class HubitatPollerGt(GwsprotoSemaType):
    hubitat_component_id: str
    device_id: int
    attributes: list[MakerAPIAttributeGt]
    web_listen_enabled: bool
    poll_period_seconds: float
    type_name: Literal["hubitat.poller.gt"] = "hubitat.poller.gt"
    version: Literal["001"] = "001"
    model_config = ConfigDict(
        extra="allow", alias_generator=snake_to_camel, populate_by_name=True
    )

from typing import Literal

from pydantic import ConfigDict

from gwsproto.enums import TelemetryName, SpaceheatUnit
from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
from gwproto.utils import snake_to_camel


class MakerAPIAttributeGt(GwsprotoSemaType):
    attribute_name: str
    channel_name: str
    node_name: str
    telemetry_name: TelemetryName = TelemetryName.WaterTempCTimes1000
    unit: SpaceheatUnit = SpaceheatUnit.Celcius
    exponent: int = 3
    interpret_as_number: bool = True
    enabled: bool = True
    web_poll_enabled: bool = True
    web_listen_enabled: bool = True
    report_missing: bool = True
    report_parse_error: bool = True
    type_name: Literal["maker.api.attribute.gt"] = "maker.api.attribute.gt"
    version: Literal["000"] = "000"

    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True,
        alias_generator=snake_to_camel,
        populate_by_name=True,
    )

class HubitatPollerGt(GwsprotoSemaType):
    hubitat_component_id: str
    device_id: int
    attributes: list[MakerAPIAttributeGt] = []
    enabled: bool = True
    web_listen_enabled: bool = True
    poll_period_seconds: float = 60
    type_name: Literal["hubitat.poller.gt"] = "hubitat.poller.gt"
    version: Literal["000"] = "000"
    model_config = ConfigDict(
        extra="allow", alias_generator=snake_to_camel, populate_by_name=True
    )

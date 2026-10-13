from typing import Literal
from pydantic import StrictFloat
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PositiveInt
from sema_snapshot.sema.property_format import UUID4Str
from sema_snapshot.sema.types.maker_api_attribute_gt import MakerApiAttributeGt


class HubitatPollerGt(SemaType):
    """Sema: https://schemas.electricity.works/types/hubitat.poller.gt/001"""

    hubitat_component_id: UUID4Str
    device_id: PositiveInt
    attributes: list[MakerApiAttributeGt]
    web_listen_enabled: bool
    poll_period_seconds: StrictFloat
    type_name: Literal["hubitat.poller.gt"] = "hubitat.poller.gt"
    version: Literal["001"] = "001"

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, StrictInt
from sema_snapshot.sema.base import SemaType
from sema_snapshot.sema.property_format import PascalCase
from sema_snapshot.sema.property_format import UUID4Str


class WebServer(BaseModel):
    model_config = ConfigDict(
        alias_generator=SemaType.model_config.get("alias_generator"),
        populate_by_name=True,
        extra="forbid",
    )

    serve: bool
    host: str
    name: str
    port: StrictInt
    kwargs: dict[str, Any]


class WebServerComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/web.server.component.gt/001"""

    component_id: UUID4Str
    device_type: PascalCase
    web_server: WebServer
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["web.server.component.gt"] = "web.server.component.gt"
    version: Literal["001"] = "001"

from typing import Literal

from gwsproto.type_helpers.component_base import DeviceComponentBase
from gwproto.named_types.web_server_gt import WebServerGt


class WebServerComponentGt(DeviceComponentBase):
    WebServer: WebServerGt
    TypeName: Literal["web.server.component.gt"] = "web.server.component.gt"
    Version: Literal["001"] = "001"

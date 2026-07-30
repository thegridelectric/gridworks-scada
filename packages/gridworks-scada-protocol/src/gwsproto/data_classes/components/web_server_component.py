from typing import Any

from gwsproto.data_classes.components.component import DeviceComponent
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt
from gwproto.named_types.web_server_gt import WebServerGt


class WebServerComponent(DeviceComponent[WebServerComponentGt, Any]):
    @property
    def web_server_gt(self) -> WebServerGt:
        return self.gt.WebServer

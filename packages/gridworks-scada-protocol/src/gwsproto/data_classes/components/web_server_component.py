from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.web_server_component_gt import WebServerComponentGt
from gwsproto.named_types.web_server_gt import WebServerGt


class WebServerComponent(Component[WebServerComponentGt, ComponentAttributeClassGt]):
    @property
    def web_server_gt(self) -> WebServerGt:
        return self.gt.WebServer

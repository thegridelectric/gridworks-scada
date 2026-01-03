from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.rest_poller_component_gt import RESTPollerComponentGt
from gwsproto.named_types.rest_poller_gt import RESTPollerSettings


class RESTPollerComponent(Component[RESTPollerComponentGt, ComponentAttributeClassGt]):
    @property
    def rest(self) -> RESTPollerSettings:
        return self.gt.Rest

from typing import Any

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.rest_poller_component_gt import RESTPollerComponentGt
from gwsproto.named_types.rest_poller_gt import RESTPollerSettings


class RESTPollerComponent(Component[RESTPollerComponentGt, Any]):
    @property
    def rest(self) -> RESTPollerSettings:
        return self.gt.Rest

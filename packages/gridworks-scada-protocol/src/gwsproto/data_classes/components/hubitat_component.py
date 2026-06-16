from typing import Any, Optional

import yarl

from gwsproto.data_classes.components.component import Component
from gwsproto.named_types.hubitat_component_gt import HubitatComponentGt


class HubitatComponent(Component[HubitatComponentGt, Any]):
    web_listener_nodes: set[str]

    def __init__(
        self, gt: HubitatComponentGt, device_type: Optional[Any] = None
    ) -> None:
        super().__init__(gt, device_type)
        self.web_listener_nodes = set()

    def urls(self) -> dict[str, Optional[yarl.URL]]:
        return self.gt.urls()

    def add_web_listener(self, web_listener_node: str) -> None:
        self.web_listener_nodes.add(web_listener_node)

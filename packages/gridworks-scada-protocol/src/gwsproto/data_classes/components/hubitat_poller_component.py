from typing import Any, Optional

import yarl

from gwsproto.data_classes.components import HubitatComponent
from gwsproto.data_classes.components.component import Component
from gwsproto.data_classes.resolver import ComponentResolver
from gwsproto.data_classes.sh_node import ShNode
from gwsproto.named_types.component_attribute_class_gt import ComponentAttributeClassGt
from gwsproto.named_types.hubitat_component_gt import HubitatComponentGt
from gwsproto.named_types.hubitat_poller_component_gt import HubitatPollerComponentGt
from gwsproto.named_types.rest_poller_gt import RequestArgs, RESTPollerSettings


class HubitatPollerComponent(
    Component[HubitatPollerComponentGt, ComponentAttributeClassGt], ComponentResolver
):
    hubitat_gt: HubitatComponentGt
    _rest: Optional[RESTPollerSettings] = None

    def __init__(
        self, gt: HubitatPollerComponentGt, cac: ComponentAttributeClassGt
    ) -> None:
        super().__init__(gt, cac)
        self.hubitat_gt = HubitatComponentGt.make_stub(gt.Poller.hubitat_component_id)

    @property
    def rest(self) -> RESTPollerSettings:
        if self._rest is None:
            raise ValueError(
                f"ERROR. resolve_rest() has not yet been called for {self}."
            )
        return self._rest

    def resolve(
        self,
        node_name: str,
        _nodes: dict[str, ShNode],
        components: dict[str, Component[Any, Any]],
    ) -> None:
        if self._rest is not None:
            raise ValueError(
                f"resolve() must be called exactly once. "
                f"Rest settings already exist for {self}."
            )

        # replace proxy hubitat component, which only had component id.
        # with the actual hubitat component containing data.
        hubitat_component = components.get(self.hubitat_gt.ComponentId, None)
        if hubitat_component is None or not isinstance(
            hubitat_component, HubitatComponent
        ):
            raise ValueError(
                f"ERROR. Component for {self.hubitat_gt.ComponentId} "
                f"has type <{type(hubitat_component)}>. Expected <HubitatComponent>"
            )
        self.hubitat_gt = hubitat_component.gt

        # Constuct url config on top of maker api url url config
        self._rest = RESTPollerSettings(
            request=RequestArgs(
                url=self.hubitat_gt.refresh_url_config(self.gt.Poller.device_id)
            ),
            poll_period_seconds=self.gt.Poller.poll_period_seconds,
        )

        # register attributes which accept web posts
        if (
            self.gt.Poller.web_listen_enabled
            and hubitat_component.gt.Hubitat.WebListenEnabled
        ):
            for attribute in self.gt.Poller.attributes:
                if attribute.web_listen_enabled:
                    hubitat_component.add_web_listener(node_name)

    def urls(self) -> dict[str, Optional[yarl.URL]]:
        urls = self.hubitat_gt.urls()
        for attribute in self.gt.Poller.attributes:
            urls[attribute.node_name] = self.rest.url
        return urls

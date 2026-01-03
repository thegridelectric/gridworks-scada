import json
from typing import Sequence

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproactor import Actor
from gwproactor import Problems
from gwproactor import AppInterface
from gwproto import Message
from gwsproto.data_classes.components.hubitat_component import HubitatComponent
from gwsproto.named_types.web_server_gt import DEFAULT_WEB_SERVER_NAME
from result import Result

from actors.hubitat_interface import HubitatEventContent
from actors.hubitat_interface import HubitatWebEventHandler
from actors.hubitat_interface import HubitatWebEventListenerInterface
from actors.hubitat_interface import HubitatWebServerInterface


class Hubitat(Actor, HubitatWebServerInterface):

    _component: HubitatComponent
    _web_event_handlers: dict[tuple[int, str], HubitatWebEventHandler]
    _report_dst: str

    def __init__(
        self,
        name: str,
        services: AppInterface,
    ):
        component = services.hardware_layout.component(name)
        if not isinstance(component, HubitatComponent):
            display_name = getattr(
                component, "display_name", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> has type {type(component)}. "
                f"Expected HubitatComponent.\n"
                f"  Node: {self.name}\n"
                f"  Component id: {component.gt.ComponentId}"
            )
        self._component = component
        self._report_dst = services.name
        self._web_event_handlers = dict()
        super().__init__(name, services)
        if self._component.gt.Hubitat.WebListenEnabled:
            self._services.add_web_route(
                server_name=DEFAULT_WEB_SERVER_NAME,
                method="POST",
                path="/" + self._component.gt.Hubitat.listen_path,
                handler=self._handle_web_post,
            )
            for web_listener_node in self._component.web_listener_nodes:
                actor = self._services.get_communicator(web_listener_node)
                if actor is not None and isinstance(actor, HubitatWebEventListenerInterface):
                    self.add_web_event_handlers(actor.get_hubitat_web_event_handlers())

    def add_web_event_handler(self, handler: HubitatWebEventHandler) -> None:
        if self._component.gt.Hubitat.WebListenEnabled:
            self._web_event_handlers[(handler.device_id, handler.event_name)] = handler

    def add_web_event_handlers(self, handlers: Sequence[HubitatWebEventHandler]) -> None:
        for handler in handlers:
            self.add_web_event_handler(handler)

    # from aiohttp.web_request import Request
    async def _handle_web_post(self, request: Request) -> Response:
        try:
            text = await request.text()
        except Exception as e:
            self.services.send_threadsafe(
                Message(
                    Payload=Problems(errors=[e]).problem_event(
                        summary=(
                            f"ERROR awaiting hubitat request text <{self._name}>: {type(e)} <{e}>"
                        ),
                    )
                )
            )
        else:
            try:
                content = HubitatEventContent(
                    **json.loads(text).get("content", {})
                )
                converter = self._web_event_handlers.get(
                    (content.deviceId, content.name), None
                )
                if converter is not None:
                    message = converter(content, self._report_dst)
                    if message is not None:
                        self.services.send_threadsafe(message)
            except Exception as e: # noqa
                self.services.send_threadsafe(
                    Message(
                        Payload=Problems(
                            msg=f"request: <{text}>",
                            errors=[e]
                        ).problem_event(
                            summary=(
                                f"Hubitat event processing error for <{self._name}>: {type(e)} <{e}>"
                            ),
                        )
                    )
                )
        return Response()

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        raise ValueError("Hubitat does not currently process any messages")

    def start(self) -> None:
        """IOLoop will take care of start."""

    def stop(self) -> None:
        """IOLoop will take care of stop."""

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

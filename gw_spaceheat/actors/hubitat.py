import json
from typing import Sequence

from aiohttp.web_request import Request
from aiohttp.web_response import Response
from gwproactor import Actor
from gwproactor import AppInterface
from gwproto import Message
from gwsproto.data_classes.components.hubitat_component import HubitatComponent
from gwsproto.enums import LogLevel
from gwsproto.named_types import Glitch
from result import Result

from gwsproto.names.core.node_names import ScadaWeb
from actors.glitch_limit import REPEAT_GLITCH_S, GlitchLimit
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
        self.glitch_limit = GlitchLimit(REPEAT_GLITCH_S)
        super().__init__(name, services)
        if self._component.gt.Hubitat.WebListenEnabled:
            self._services.add_web_route(
                server_name=ScadaWeb.DEFAULT_SERVER_NAME,
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
            self.send_warning(
                "hubitat-unreadable-post", f"{self.name} cannot read a post body: {type(e).__name__}: {e}"
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
                self.send_warning(
                    "hubitat-event-refused", f"{self.name} refused an event: {type(e).__name__}: {e}"
                )
        return Response()

    def send_warning(self, summary: str, details: str) -> None:
        """A Warning glitch to the primary scada, at most once per summary
        per REPEAT_GLITCH_S. Called on the IO loop."""
        if not self.glitch_limit.due(summary):
            return
        self.services.send_threadsafe(
            Message(
                Src=self.name,
                Dst=self._report_dst,
                Payload=Glitch(
                    FromGNodeAlias=self.services.hardware_layout.scada_g_node_alias,
                    Node=self.name,
                    Type=LogLevel.Warning,
                    Summary=summary,
                    Details=details,
                ),
            )
        )

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        raise ValueError("Hubitat does not currently process any messages")

    def start(self) -> None:
        """IOLoop will take care of start."""

    def stop(self) -> None:
        """IOLoop will take care of stop."""

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

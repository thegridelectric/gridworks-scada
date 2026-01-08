import functools
import time
from typing import Optional
from typing import Sequence

from aiohttp import ClientResponse
from aiohttp import ClientSession
from gwproactor import Actor
from gwproactor import Problems
from gwproactor import AppInterface
from gwproactor.actors.rest import RESTPoller
from gwproto import Message
from gwsproto.data_classes.components.hubitat_component import HubitatComponent
from gwsproto.data_classes.components.hubitat_poller_component import HubitatPollerComponent
from gwsproto.type_helpers import MakerAPIAttributeGt
from result import Err
from result import Ok
from result import Result

from actors.hubitat_interface import default_float_converter
from actors.hubitat_interface import HubitatAttributeConvertFailure
from actors.hubitat_interface import HubitatAttributeMissing
from actors.hubitat_interface import HubitatWebEventHandler
from actors.hubitat_interface import HubitatWebEventListenerInterface
from actors.hubitat_interface import HubitatWebServerInterface
from actors.hubitat_interface import MakerAPIRefreshResponse
from actors.hubitat_interface import ValueConverter
from gwsproto.named_types import SyncedReadings




class HubitatRESTPoller(RESTPoller):

    _last_read_time: float
    _report_dst: str
    _component: HubitatPollerComponent
    _value_converters: dict[str, ValueConverter]

    def __init__(
            self,
            name: str,
            component: HubitatPollerComponent,
            services: AppInterface,
    ):
        self._report_dst = services.name
        self._component = component
        super().__init__(
            name,
            self._component.rest,
            services.io_loop_manager,
            convert=self._hubitat_response_converter,
            forward=services.send_threadsafe,
        )
        self._value_converters = dict()

    def set_value_converters(self, converters: dict[str, ValueConverter]):
        self._value_converters = dict(converters)

    async def _make_request(self, session: ClientSession) -> Optional[ClientResponse]:
        """"We assume a refresh sent to hubitat returns the value of the *last* refresh,
        so we just send two refreshes.
        """
        response = await super()._make_request(session)
        if response is None:
            return None
        else:
            async with response:
                self._last_read_time = time.time()
            return await super()._make_request(session)

    @classmethod
    def _convert_attribute(
        cls,
        config_attribute: MakerAPIAttributeGt,
        response: MakerAPIRefreshResponse,
        converter: ValueConverter,
    ) -> Result[Optional[int], BaseException]:
        response_attribute = response.get_attribute_by_name(
            config_attribute.attribute_name
        )
        if response_attribute is None:
            if config_attribute.report_missing:
                return Err(HubitatAttributeMissing(
                    config_attribute.node_name,
                    config_attribute.attribute_name
                ))
        try:
            return Ok(converter(response_attribute.currentValue))
        except BaseException as e:
            return Err(HubitatAttributeConvertFailure(
                config_attribute.node_name,
                config_attribute.attribute_name,
                response_attribute.currentValue,
                str(e)
            ))

    async def _hubitat_response_converter(self, response: ClientResponse) -> Optional[Message]:
        try:
            response = MakerAPIRefreshResponse(
                **await response.json(content_type=None)
            )
            about_channels = []
            values = []
            warnings = []
            for config_attribute in self._component.gt.Poller.attributes:
                if (config_attribute.enabled and
                    config_attribute.web_poll_enabled and
                    config_attribute.attribute_name in self._value_converters
                ):
                    convert_result = self._convert_attribute(
                        config_attribute,
                        response,
                        self._value_converters[config_attribute.attribute_name],
                    )
                    if convert_result.is_ok():
                        if convert_result.value is not None:
                            about_channels.append(config_attribute.channel_name)
                            values.append(convert_result.value)
                    else:
                        warnings.append(convert_result.err())
            if values:
                return Message(
                    Src=self._name,
                    Dst=self._report_dst,
                    Payload=SyncedReadings(
                        ChannelNameList=about_channels,
                        ValueList=values,
                        ScadaReadTimeUnixMs=int(1000 * time.time())
                    )
                )
            if warnings:
                self._forward(
                    Message(
                        Payload=Problems(warnings=warnings).problem_event(
                            summary=(
                                f"<{self._name}> _convert() warnings "
                            )
                        )
                    )
                )
        except BaseException as e:
            self._forward(
                Message(
                    Payload=Problems(errors=[e]).problem_event(
                        summary=(
                            f"<{self._name}> _convert() error"
                        )
                    )
                )
            )
        return None

class HubitatPoller(Actor, HubitatWebEventListenerInterface):

    _component: HubitatPollerComponent
    _poller: HubitatRESTPoller
    _web_event_handlers: list[HubitatWebEventHandler]

    def __init__(
        self,
        name: str,
        services: AppInterface,
    ):
        component = services.hardware_layout.component(name)
        if not isinstance(component, HubitatPollerComponent):
            display_name = getattr(
                component, "display_name", "MISSING ATTRIBUTE display_name"
            )
            raise ValueError(
                f"ERROR. Component <{display_name}> has type {type(component)}. "
                f"Expected HubitatPollerComponent.\n"
                f"  Node: {name}\n"
                f"  Component id: {component.gt.ComponentId}"
            )

        super().__init__(name, services)
        self._component = component
        self._poller = HubitatRESTPoller(
                name=name,
                component=component,
                services=services,
            )
        self._web_event_handlers = []

    def init(self):
        """Iterate over configured attributes, create value converters for them and
        assign them to poller and hubitat web server per configuration.

        This is called outside the constructor so that the derived class can control
        creation non-numerical attribute converters by overloading
        _make_non_numerical_value_converter()
        """
        poll_value_converters = dict()
        handlers = []
        if self._component.gt.Poller.enabled:
            for attribute in self._component.gt.Poller.attributes:
                if attribute.enabled:
                    if (converter := self._make_value_converter(attribute)) is not None:
                        if attribute.web_poll_enabled:
                            poll_value_converters[attribute.attribute_name] = converter
                        if attribute.web_listen_enabled:
                            handlers.append(
                                HubitatWebEventHandler(
                                    device_id=self._component.gt.Poller.device_id,
                                    event_name=attribute.attribute_name,
                                    report_src_node_name=self.name,
                                    channel_name=attribute.channel_name,
                                    value_converter=converter,
                                )
                            )
        if poll_value_converters:
            self._poller.set_value_converters(poll_value_converters)
        if handlers:
            self._web_event_handlers = handlers
            if (hubitat_actor := self._get_hubitat_actor()) is not None:
                hubitat_actor.add_web_event_handlers(self._web_event_handlers)

    def _make_non_numerical_value_converter(self, attribute: MakerAPIAttributeGt) -> Optional[ValueConverter]: # noqa
        return None

    def _make_value_converter(self, attribute: MakerAPIAttributeGt) -> Optional[ValueConverter]:
        if attribute.enabled:
            if attribute.interpret_as_number:
                return functools.partial(default_float_converter, exponent=attribute.exponent)
            else:
                return self._make_non_numerical_value_converter(attribute)
        return None

    def _get_hubitat_actor(self) -> Optional[HubitatWebServerInterface]:
        hubitat_actor = None
        if self._component.gt.Poller.web_listen_enabled:
            hubitat_component = self._services.hardware_layout.get_component_as_type(
                self._component.gt.Poller.hubitat_component_id,
                HubitatComponent
            )
            if hubitat_component is not None:
                hubitat_node = self._services.hardware_layout.node_from_component(
                    hubitat_component.gt.ComponentId
                )
                if hubitat_node is not None:
                    hubitat_actor = self._services.get_communicator_as_type(
                        hubitat_node.Name,
                        HubitatWebServerInterface
                    )
        return hubitat_actor

    def get_hubitat_web_event_handlers(self) -> Sequence[HubitatWebEventHandler]:
        return self._web_event_handlers

    def process_message(self, message: Message) -> Result[bool, BaseException]:
        raise ValueError("HubitatTankModule does not currently process any messages")

    def start(self) -> None:
        if self._component.gt.Poller.enabled:
            self._poller.start()

    def stop(self) -> None:
        if self._component.gt.Poller.enabled:
            try:
                self._poller.stop()
            except: # noqa
                pass

    async def join(self) -> None:
        """IOLoop will take care of shutting down the associated task."""

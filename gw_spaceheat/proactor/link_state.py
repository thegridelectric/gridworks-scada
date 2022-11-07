import abc
import enum
from dataclasses import dataclass
from typing import Optional
from typing import Sequence

from result import Err
from result import Ok
from result import Result

from gwproto import Message

from proactor.message import MQTTConnectFailPayload
from proactor.message import MQTTConnectPayload
from proactor.message import MQTTDisconnectPayload
from proactor.message import MQTTReceiptPayload
from proactor.message import MQTTSubackPayload


class StateName(enum.Enum):
    none = "none"
    not_started = "not_started"
        # start()                               ->  start_called         (1)       -> connecting                   *** which start()?

    connecting = "connecting"
        # _process_mqtt_connected               -> mqtt_connected        (2)       -> awaiting_setup_and_peer
        # _process_mqtt_connect_fail            -> mqtt_connect_failed   (3)       -> connecting

    awaiting_setup_and_peer = "awaiting_setup_and_peer"
        # _process_mqtt_suback                  -> mqtt_suback           (4)      -> awaiting_setup_and_peer
        # _process_mqtt_suback                  -> mqtt_suback           (5)      -> awaiting_peer
        # _process_mqtt_message                 -> message_from_peer     (6)      -> awaiting_setup
        # _process_mqtt_disconnected            -> mqtt_disconnected     (7)      -> connecting
        # _process_ack_timeout                  -> response_timeout     (17)      -> awaiting_setup_and_peer

    awaiting_setup = "awaiting_setup"
        # _process_mqtt_suback                  -> mqtt_suback           (8)      -> awaiting_setup
        # _process_mqtt_suback                  -> mqtt_suback           (9)      -> active
        # _process_ack_timeout                  -> response_timeout     (10)      -> awaiting_setup_and_peer
        # _process_mqtt_disconnected            -> mqtt_disconnected    (11)      -> connecting
        # _process_mqtt_message                 -> message_from_peer    (16)      -> awaiting_setup

    awaiting_peer = "awaiting_peer"
        # _process_mqtt_message                 -> message_from_peer    (12)      -> awaiting_setup
        # _process_mqtt_disconnected            -> mqtt_disconnected    (13)      -> connecting
        # _process_ack_timeout                  -> response_timeout     (19)      -> awaiting_peer

    active = "active"
        # _process_ack_timeout                  -> response_timeout     (14)      -> awaiting_peer
        # _process_mqtt_disconnected            -> mqtt_disconnected    (15)      -> connecting

    stopped = "stopped"
        # stop()                               ->  stop_called          (18)      -> stopped                   *** which stop()?

class TransitionName(enum.Enum):
    none = "none"
    start_called = "start_called"
    mqtt_connected = "mqtt_connected"
    mqtt_connect_failed = "mqtt_connect_failed"
    mqtt_disconnected = "mqtt_disconnected"
    mqtt_suback = "mqtt_suback"
    message_from_peer = "message_from_peer"
    response_timeout = "response_timeout"
    stop_called = "stop_called"

@dataclass
class Transition:
    link_name: str = ""
    transition_name: TransitionName = TransitionName.none
    old_state: StateName = StateName.not_started
    new_state: StateName = StateName.not_started

    def __bool__(self) -> bool:
        return self.old_state != self.new_state

    def active(self):
        return self.new_state == StateName.active

    def activated(self):
        return self.old_state != StateName.active and self.new_state == StateName.active

    def deactivated(self):
        return self.old_state == StateName.active and self.new_state != StateName.active

class InvalidCommStateInput(Exception):
    name: str = ""
    current_state: StateName = StateName.none
    transition: TransitionName = TransitionName.none

    def __init__(
        self,
        name: str = "",
        current_state: StateName = StateName.none,
        transition: TransitionName = TransitionName.none,
        *,
        msg: str = "",
    ):
        self.name = name
        self.current_state = current_state
        self.transition = transition
        super().__init__(msg)

    def __str__(self):
        s = self.__class__.__name__
        super_str = super().__str__()
        if super_str:
            s += f" [{super_str}]"
        s += f"  for link: [{self.name}]  current state:{self.current_state}  requested transition: {self.transition}"
        return s

class CommLinkMissing(InvalidCommStateInput):
    def __init__(self, name: str, *, msg=""):
        super().__init__(name, msg=msg)

class CommLinkAlreadyExists(InvalidCommStateInput):
    ...

class RuntimeLinkStateError(InvalidCommStateInput):
    ...

class State(abc.ABC):
    """By default all transitions disallowed except stopping, which is always allowed and leads to stopped."""

    @property
    @abc.abstractmethod
    def name(self) -> StateName:
        raise NotImplementedError

    def start(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.start_called))

    def stop(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.stop_called, self.name, StateName.stopped))

    def process_mqtt_connected(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.mqtt_connected))

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.mqtt_disconnected))

    def process_mqtt_connect_fail(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.mqtt_connect_failed))

    def process_mqtt_suback(self, num_pending_subscriptions: int) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.mqtt_suback))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.message_from_peer))

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return Err(InvalidCommStateInput("", current_state=self.name, transition=TransitionName.response_timeout))

class NotStarted(State):

    @property
    def name(self) -> StateName:
        return StateName.not_started

    def start(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.start_called, self.name, StateName.connecting))

class Connecting(State):

    @property
    def name(self) -> StateName:
        return StateName.connecting

    def process_mqtt_connected(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_connected, self.name, StateName.awaiting_setup_and_peer))

    def process_mqtt_connect_fail(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_connect_failed, self.name, StateName.connecting))

class AwaitingSetupAndPeer(State):
    @property
    def name(self) -> StateName:
        return StateName.awaiting_setup_and_peer

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_disconnected, self.name, StateName.connecting))

    def process_mqtt_suback(self, num_pending_subscriptions: int) -> Result[Transition, InvalidCommStateInput]:
        if num_pending_subscriptions == 0:
            new_state = StateName.awaiting_peer
        else:
            new_state = self.name
        return Ok(Transition("", TransitionName.mqtt_suback, self.name, new_state))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.message_from_peer, self.name, StateName.awaiting_setup))

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.response_timeout, self.name, self.name))

class AwaitingSetup(State):

    @property
    def name(self) -> StateName:
        return StateName.awaiting_setup

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_disconnected, self.name, StateName.connecting))

    def process_mqtt_suback(self, num_pending_subscriptions: int) -> Result[Transition, InvalidCommStateInput]:
        if num_pending_subscriptions == 0:
            new_state = StateName.active
        else:
            new_state = self.name
        return Ok(Transition("", TransitionName.mqtt_suback, self.name, new_state))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.message_from_peer, self.name, self.name))

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.response_timeout, self.name, StateName.awaiting_setup_and_peer))

class AwaitingPeer(State):
    @property
    def name(self) -> StateName:
        return StateName.awaiting_peer

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_disconnected, self.name, StateName.connecting))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.message_from_peer, self.name, StateName.active))

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.response_timeout, self.name, self.name))

class Active(State):
    @property
    def name(self) -> StateName:
        return StateName.active

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.mqtt_disconnected, self.name, StateName.connecting))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.message_from_peer, self.name, StateName.active))

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return Ok(Transition("", TransitionName.response_timeout, self.name, StateName.awaiting_peer))

class Stopped(State):
    @property
    def name(self) -> StateName:
        return StateName.stopped

class Link:
    name: str
    states: dict[StateName, State]
    curr_state: State

    def __init__(self, name, curr_state: StateName = StateName.not_started):
        self.name = name
        self.states = {
            state.name: state for state in [
                NotStarted(),
                Connecting(),
                AwaitingSetupAndPeer(),
                AwaitingSetup(),
                AwaitingPeer(),
                Active(),
                Stopped(),
            ]
        }
        self.curr_state = self.states[curr_state]

    @property
    def state(self) -> StateName:
        return self.curr_state.name

    def _handle(self, result) -> Result[Transition, InvalidCommStateInput]:
        match result:
            case Ok(transition):
                transition.link_name = self.name
                self.curr_state = self.states[result.unwrap().new_state]
            case Err(exception):
                exception.name = self.name
        return result

    def start(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.start())

    def stop(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.stop())

    def process_mqtt_connected(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_mqtt_connected())

    def process_mqtt_disconnected(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_mqtt_disconnected())

    def process_mqtt_connect_fail(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_mqtt_connect_fail())

    def process_mqtt_suback(self, num_pending_subscriptions: int) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_mqtt_suback(num_pending_subscriptions))

    def process_mqtt_message(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_mqtt_message())

    def process_ack_timeout(self) -> Result[Transition, InvalidCommStateInput]:
        return self._handle(self.curr_state.process_ack_timeout())

class Links:
    _links: dict[str, Link]

    def __init__(self, names: Optional[Sequence[str]] = None):
        self._links = dict()
        if names is not None:
            for name in names:
                self.add(name)

    def link(self, name) -> Optional[Link]:
        return self._links.get(name, None)

    def link_state(self, name) -> Optional[StateName]:
        if name in self._links:
            return self._links[name].curr_state.name
        return None

    def __contains__(self, name: str) -> bool:
        return name in self._links

    def __getitem__(self, name: str) -> Link:
        try:
            return self._links[name]
        except KeyError:
            raise CommLinkMissing(name)

    def add(self, name: str, state: StateName = StateName.not_started) -> Link:
        if name in self._links:
            raise CommLinkAlreadyExists(name, current_state=self._links[name].curr_state.name)
        self._links[name] = Link(name, state)
        return self._links[name]

    def start(self, name:str) -> Result[Transition, InvalidCommStateInput]:
        return self[name].start()

    def stop(self, name: str) -> Result[Transition, InvalidCommStateInput]:
        return self[name].stop()

    def process_mqtt_connected(self, message: Message[MQTTConnectPayload]) -> Result[Transition, InvalidCommStateInput]:
        return self[message.Payload.client_name].process_mqtt_connected()

    def process_mqtt_disconnected(self, message: Message[MQTTDisconnectPayload]) -> Result[Transition, InvalidCommStateInput]:
        return self[message.Payload.client_name].process_mqtt_disconnected()

    def process_mqtt_connect_fail(self, message: Message[MQTTConnectFailPayload]) -> Result[Transition, InvalidCommStateInput]:
        return self[message.Payload.client_name].process_mqtt_connect_fail()

    def process_mqtt_suback(self, message: Message[MQTTSubackPayload]) -> Result[Transition, InvalidCommStateInput]:
        return self[message.Payload.client_name].process_mqtt_suback(message.Payload.num_pending_subscriptions)

    def process_mqtt_message(self, message: Message[MQTTReceiptPayload]) -> Result[Transition, InvalidCommStateInput]:
        return self[message.Payload.client_name].process_mqtt_message()

    def process_ack_timeout(self, name: str) -> Result[Transition, InvalidCommStateInput]:
        return self[name].process_ack_timeout()



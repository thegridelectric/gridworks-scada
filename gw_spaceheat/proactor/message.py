"""Message structures for use between proactor and its sub-objects."""
from enum import Enum
from typing import Any
from typing import Dict
from typing import Generic
from typing import List
from typing import Optional
from typing import TypeVar

from gwproto.message import Message, Header
from paho.mqtt.client import MQTTMessage
from pydantic import BaseModel

class MessageType(Enum):
    invalid = "invalid"
    mqtt_subscribe = "mqtt_subscribe"
    mqtt_message = "mqtt_message"

    mqtt_connected = "mqtt_connected"
    mqtt_disconnected = "mqtt_disconnected"
    mqtt_connect_failed = "mqtt_connect_failed"

    mqtt_suback = "mqtt_suback"

    event_report = "event_report"

class KnownNames(Enum):
    proactor = "proactor"
    mqtt_clients = "mqtt_clients"

class MQTTClientsPayload(BaseModel):
    client_name: str
    userdata: Optional[Any]


MQTTClientsPayloadT = TypeVar("MQTTClientsPayloadT", bound=MQTTClientsPayload)


class MQTTClientMessage(Message[MQTTClientsPayloadT], Generic[MQTTClientsPayloadT]):
    def __init__(
        self,
        message_type: MessageType,
        payload: MQTTClientsPayloadT,
    ):
        super().__init__(
            header=Header(
                src=KnownNames.mqtt_clients.value,
                dst=KnownNames.proactor.value,
                message_type=message_type.value,
            ),
            payload=payload,
        )


class MQTTMessageModel(BaseModel):
    timestamp: float = 0
    state: int = 0
    dup: bool = False
    mid: int = 0
    topic: str = ""
    payload: bytes = bytes()
    qos: int = 0
    retain: bool = False

    @classmethod
    def from_mqtt_message(cls, message: MQTTMessage) -> "MQTTMessageModel":
        model = MQTTMessageModel()
        for field_name in model.__fields__:
            setattr(model, field_name, getattr(message, field_name))
        return model


class MQTTReceiptPayload(MQTTClientsPayload):
    message: MQTTMessageModel


class MQTTReceiptMessage(MQTTClientMessage[MQTTReceiptPayload]):
    def __init__(
        self,
        client_name: str,
        userdata: Optional[Any],
        message: MQTTMessage,
    ):
        super().__init__(
            message_type=MessageType.mqtt_message,
            payload=MQTTReceiptPayload(
                client_name=client_name,
                userdata=userdata,
                message=MQTTMessageModel.from_mqtt_message(message),
            ),
        )


class MQTTSubackPayload(MQTTClientsPayload):
    mid: int
    granted_qos: List[int]
    num_pending_subscriptions: int


class MQTTSubackMessage(MQTTClientMessage[MQTTSubackPayload]):
    def __init__(
        self,
        client_name: str,
        userdata: Optional[Any],
        mid: int,
        granted_qos: List[int],
        num_pending_subscriptions: int,
    ):
        super().__init__(
            message_type=MessageType.mqtt_suback,
            payload=MQTTSubackPayload(
                client_name=client_name,
                userdata=userdata,
                mid=mid,
                granted_qos=granted_qos,
                num_pending_subscriptions=num_pending_subscriptions,
            ),
        )


class MQTTCommEventPayload(MQTTClientsPayload):
    rc: int


class MQTTConnectPayload(MQTTCommEventPayload):
    flags: Dict


class MQTTConnectMessage(MQTTClientMessage[MQTTConnectPayload]):
    def __init__(
        self,
        client_name: str,
        userdata: Optional[Any],
        flags: Dict,
        rc: int,
    ):
        super().__init__(
            message_type=MessageType.mqtt_connected,
            payload=MQTTConnectPayload(
                client_name=client_name,
                userdata=userdata,
                flags=flags,
                rc=rc,
            ),
        )


class MQTTConnectFailPayload(MQTTClientsPayload):
    pass


class MQTTConnectFailMessage(MQTTClientMessage[MQTTConnectFailPayload]):
    def __init__(self, client_name: str, userdata: Optional[Any]):
        super().__init__(
            message_type=MessageType.mqtt_connect_failed,
            payload=MQTTConnectFailPayload(
                client_name=client_name,
                userdata=userdata,
            ),
        )


class MQTTDisconnectPayload(MQTTCommEventPayload):
    pass


class MQTTDisconnectMessage(MQTTClientMessage[MQTTDisconnectPayload]):
    def __init__(self, client_name: str, userdata: Optional[Any], rc: int):
        super().__init__(
            message_type=MessageType.mqtt_disconnected,
            payload=MQTTDisconnectPayload(
                client_name=client_name,
                userdata=userdata,
                rc=rc,
            ),
        )


# class EventBase(BaseModel):
#     message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
#     time_ns: int = Field(default_factory=time.time_ns)
#     src: str = ""
#     type_name: str = Field(const=True)
#
#
# EventT = TypeVar("EventT", bound=EventBase)
#
#
# class StartupEvent(EventBase):
#     clean_shutdown: bool
#     type_name: Literal["gridworks.event.startup.000"] = "gridworks.event.startup.000"
#
#
# class ShutdownEvent(EventBase):
#     reason: str
#     type_name: Literal["gridworks.event.shutdown.000"] = "gridworks.event.shutdown.000"
#
#
# class Problems(Enum):
#     error = "error"
#     warning = "warning"
#
#
# class ProblemEvent(EventBase):
#     problem_type: Problems
#     summary: str
#     details: str = ""
#     type_name: Literal["gridworks.event.problem.000"] = "gridworks.event.problem.000"
#
#     @validator("problem_type", pre=True)
#     def problem_type_value(cls, v):
#         return as_enum(v, Problems)
#
#
# class CommEvent(EventBase):
#     ...
#
#
# class MQTTCommEvent(CommEvent):
#     ...
#
#
# class MQTTConnectFailedEvent(MQTTCommEvent):
#     type_name: Literal["gridworks.event.comm.mqtt.connect_failed.000"] = "gridworks.event.comm.mqtt.connect_failed.000"
#
#
# class MQTTDisconnectEvent(MQTTCommEvent):
#     type_name: Literal["gridworks.event.comm.mqtt.disconnect.000"] = "gridworks.event.comm.mqtt.disconnect.000"
#
#
# class MQTTFullySubscribedEvent(CommEvent):
#     type_name: Literal["gridworks.event.comm.mqtt.fully_subscribed.000"] = "gridworks.event.comm.mqtt.fully_subscribed.000"
#
#
# class EventMessage(Message[EventT], Generic[EventT]):
#     ...
#
#
# class Ack(BaseModel):
#     acks_message_id: str = ""
#     type_name: Literal["gridworks.ack.000"] = "gridworks.ack.000"

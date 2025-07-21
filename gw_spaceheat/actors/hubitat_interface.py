import abc
from enum import Enum
from typing import Any
from typing import Callable
from typing import Optional
from typing import Sequence
from typing import TypeVar

from gwproto import Message
from pydantic import ConfigDict, BaseModel

from gwproto.named_types import SyncedReadings
from drivers.exceptions import DriverWarning


class HubitatAttributeWarning(DriverWarning):
    """An expected attribute was missing from a Hubitat refresh response"""

    node_name: str
    attribute_name: str

    def __init__(
            self,
            node_name: str,
            attribute_name: str,
            msg: str = "",
    ):
        super().__init__(msg)
        self.node_name = node_name
        self.attribute_name = attribute_name

    def __str__(self):
        s = self.__class__.__name__
        super_str = super().__str__()
        if super_str:
            s += f" <{super_str}>"
        s += (
            f" Attribute: <{self.attribute_name}> "
            f" Node: <{self.node_name}>"
        )
        return s

class HubitatAttributeMissing(HubitatAttributeWarning):
    """An expected attribute was missing from a Hubitat refresh response"""

    def __str__(self):
        return "Missing Attribute  " + super().__str__()

HubitatValueType = Optional[str | float | int]

class HubitatAttributeConvertFailure(HubitatAttributeWarning):
    """An expected attribute was missing from a Hubitat refresh response"""

    received: Optional[str | int | float]

    def __init__(
            self,
            node_name: str,
            attribute_name: str,
            received: HubitatValueType,
            msg: str = "",
    ):
        super().__init__(
            node_name=node_name,
            attribute_name=attribute_name,
            msg=msg
        )
        self.received = received

    def __str__(self):
        return "Convert failure Attribute  received: {}" + super().__str__()


class MakerAPIAttribute(BaseModel, extra="allow"):
    name: str = ""
    currentValue: HubitatValueType = None
    dataType: str = ""

class MakerAPIRefreshResponse(BaseModel, extra="allow"):
    id: int
    name: str = ""
    label: str = ""
    type: str = ""
    attributes: list[MakerAPIAttribute]

    def get_attribute_by_name(self, name: str) -> Optional[MakerAPIAttribute]:
        return next((attr for attr in self.attributes if attr.name == name), None)


class HubitatEventContent(BaseModel):
    name: str
    value: HubitatValueType
    displayName: Optional[str] = None
    deviceId: int
    descriptionText: Optional[str] = None
    unit: Optional[str] = None
    type: Optional[Any] = None
    data: Optional[Any] = None
    model_config = ConfigDict(extra="allow")

ValueConverter = Callable[[HubitatValueType], Optional[int]]

def default_float_converter(value: HubitatValueType, exponent: int) -> Optional[int]:
    try:
        return int(float(value) * pow(10, exponent))
    except: # noqa
        ...
    return None

EnumT = TypeVar("EnumT", bound=Enum)


def default_mapping_converter(
    value: HubitatValueType,
    mapping: dict[str, int],
    default: Optional[int] = None,
    raise_missing: bool = False,
) -> Optional[int]:
    str_value = str(value)
    if str_value in mapping:
        return int(mapping[str_value])
    elif raise_missing:
        raise ValueError(f"Value {value} missing from mapping {mapping}")
    return default

def default_enum_converter(
        value: HubitatValueType,
        enum_type: EnumT,
        default: Optional[int] = None
) -> Optional[int]:
    return default_mapping_converter(
        value,
        mapping={name: int(value.value) for name, value in enum_type.__members__.items()},
        default=default,
    )


class HubitatWebEventHandler(BaseModel):
    device_id: int
    event_name: str
    report_src_node_name: str
    channel_name: str
    value_converter: ValueConverter

    def __call__(self, event: HubitatEventContent, report_dst: str) -> Optional[Message]:
        message = None
        try:
            value = self.value_converter(event.value)
            if value is not None:
                message = Message(
                    Src=self.report_src_node_name,
                    Dst=report_dst,
                    Payload=SyncedReadings(
                        ChannelNameList=[self.channel_name],
                        ValueList=[value],
                        ScadaReadTimeUnixMs=int(1000 * time.time())
                    )
                )
        except: # noqa
            pass
        return message

class HubitatWebEventListenerInterface(abc.ABC):
    def get_hubitat_web_event_handlers(self) -> Sequence[HubitatWebEventHandler]:
        """Return any hubitat web event handlers"""


class HubitatWebServerInterface(abc.ABC):
    def add_web_event_handlers(self, handlers: Sequence[HubitatWebEventHandler]) -> None:
        """Register handlers for hubitat web events"""

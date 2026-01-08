from typing import NamedTuple

from pydantic import BaseModel

from gwsproto.data_classes.sh_node import ShNode
from gwsproto.enums import TelemetryName
from gwsproto.property_format import SpaceheatName


class TelemetryTuple(NamedTuple):
    AboutNode: ShNode
    SensorNode: ShNode
    TelemetryName: TelemetryName

    def __repr__(self) -> str:
        return f"TT({self.AboutNode.name} {self.TelemetryName} read by {self.SensorNode.name})"


class ChannelStub(BaseModel):
    Name: SpaceheatName
    AboutNodeName: SpaceheatName
    TelemetryName: TelemetryName
    InPowerMetering: bool = False

    def __hash__(self) -> int:
        return hash(self.Name)

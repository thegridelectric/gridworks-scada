from pydantic import BaseModel
from typing import Sequence
from gwsproto.property_format import SpaceheatName


class ZoneConfig(BaseModel):
    name: SpaceheatName


class ZonesConfig(BaseModel):
    zones: Sequence[ZoneConfig]
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gwsproto.property_format import SpaceheatName


class Gw1HvacZone(BaseModel):
    """
    Sema: https://schemas.electricity.works/types/gw1.hvac.zone/000

    One heating zone of a hydronic layout: its label, whether it is a critical
    (must-keep-warm) zone, and its thermal weight (kWh per degree F). A layout's
    zones are an ordered list; the 1-based position is the zone index used to name
    the zone's temp/set/heat-call channels. Shared across House0 and Nolan.
    Hand-ported from the gwta sema snapshot runtime (gw1.hvac.zone/000).
    """

    Name: SpaceheatName
    Critical: bool
    KwhPerDegF: float
    TypeName: Literal["gw1.hvac.zone"] = "gw1.hvac.zone"
    Version: Literal["000"] = "000"
    model_config = ConfigDict(extra="allow")

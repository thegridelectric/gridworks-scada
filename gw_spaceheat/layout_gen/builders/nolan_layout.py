from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from gwsproto.property_format import  LeftRightDotStr, SpaceheatName
from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZones
from layout_gen.core.layout_db import LayoutDb 
from layout_gen.base_layout_gen import ZoneWhitewireNames
from layout_gen.builders.gw108_layout_gen import (
    add_whitewire_zone,
    GW108_WHITEWIRE_GPIO_PINS,
)


@dataclass(frozen=True)
class NolanGw108Spec:
    """
    This is the only place that should know:
      - zone list
      - which GPIO pin corresponds to each zone's whitewire opto input
      - the gw108 ComponentAttributeClassId being used
    """
    terminal_asset_alias: LeftRightDotStr
    zone_list: Sequence[SpaceheatName]


def add_nolan_whitewire_zones(db: LayoutDb, spec: NolanGw108Spec) -> None:
    """ Add whitewire sensing stack for each Nolan zone and 
    ensures layout defaults exist for zone configuration"""

    db.misc["ZoneList"] = list(spec.zone_list)
    db.misc.setdefault("ZoneKwhPerDegFList", [1 for _ in spec.zone_list])
    db.misc.setdefault("CriticalZoneList", list(spec.zone_list))

    zones = HydronicSpaceheatZones(spec.zone_list)
    for idx in zones.nodes:

        gpio_pin = GW108_WHITEWIRE_GPIO_PINS[idx]

        add_whitewire_zone(
            db=db,
            names=names,
            gpio_pin=gpio_pin,
            terminal_asset_alias=spec.terminal_asset_alias,
        )

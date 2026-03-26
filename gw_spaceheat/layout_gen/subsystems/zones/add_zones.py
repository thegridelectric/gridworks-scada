from typing import Protocol

from layout_gen.core import LayoutDb
from layout_gen.subsystems.zones.config import ZonesConfig, ZoneConfig

from gwsproto.names.hydronic_spaceheat import (
    HydronicSpaceheatZones,
    HydronicSpaceheatZoneChannelNames,
    HydronicSpaceheatZoneNodeNames,
    
)


class ZoneImplementation(Protocol):
    def add_zone(
        self,
        db: LayoutDb,
        *,
        nodes: HydronicSpaceheatZoneNodeNames,
        channels: HydronicSpaceheatZoneChannelNames,
        cfg: ZoneConfig,
    ) -> None: ...


def add_zones(
    db: LayoutDb,
    *,
    implementation: ZoneImplementation,
    cfgs: ZonesConfig,
) -> None:
    hsz = HydronicSpaceheatZones([z.name for z in cfgs.zones])

    for idx, cfg in enumerate(cfgs.zones, start=1):
        implementation.add_zone(
            db,
            nodes=hsz.nodes[idx],
            channels=hsz.channels[idx],
            cfg=cfg,
        )
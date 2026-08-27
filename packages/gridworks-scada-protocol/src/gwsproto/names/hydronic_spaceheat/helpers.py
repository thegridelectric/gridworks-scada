from typing import Sequence

from gwsproto.property_format import SpaceheatName
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatZoneNodeNames, TankNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatZoneChannelNames, TankChannelNames


class HydronicSpaceheatZones:

    def __init__(self, zone_names: Sequence[SpaceheatName]):

        self.nodes: dict[int, HydronicSpaceheatZoneNodeNames] = {}
        self.channels: dict[int, HydronicSpaceheatZoneChannelNames] = {}

        for idx, name in enumerate(zone_names, start=1):

            self.nodes[idx] = HydronicSpaceheatZoneNodeNames(name, idx)
            self.channels[idx] = HydronicSpaceheatZoneChannelNames(name, idx)



class Tanks:

    def __init__(self, total_store_tanks: int):
        self.nodes: dict[int, TankNodeNames] = {}
        self.channels: dict[int, TankChannelNames] = {}

        for idx in range(total_store_tanks):
            self.nodes[idx+1] = TankNodeNames(idx + 1)
            self.channels[idx+1] = TankChannelNames(idx + 1)








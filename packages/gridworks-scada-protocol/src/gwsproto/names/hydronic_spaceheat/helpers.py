from gwsproto.names.hydronic_spaceheat.node_names import TankNodeNames
from gwsproto.names.hydronic_spaceheat.channel_names import TankChannelNames


class Tanks:

    def __init__(self, total_store_tanks: int):
        self.nodes: dict[int, TankNodeNames] = {}
        self.channels: dict[int, TankChannelNames] = {}

        for idx in range(total_store_tanks):
            self.nodes[idx+1] = TankNodeNames(idx + 1)
            self.channels[idx+1] = TankChannelNames(idx + 1)








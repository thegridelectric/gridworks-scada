from typing import Iterable

from gwsproto.names.hydronic_spaceheat.channel_names import TankChannelNames
from gwsproto.names.hydronic_spaceheat.node_names import TankNodeNames


def store_tanks(node_names: Iterable[str]) -> dict[int, TankChannelNames]:
    """The store tanks a layout carries, by tank index: a tank is present
    when its reader node (tank1 .. tank6) is one of the layout's node names.
    Empty for a layout with no water store tanks."""
    names = set(node_names)
    return {
        idx: TankChannelNames(idx)
        for idx in range(1, 7)
        if TankNodeNames(idx).reader in names
    }

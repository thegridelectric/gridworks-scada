from typing import Protocol



from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames as HNN
from gwsproto.names.hydronic_spaceheat.helpers import (
 BufferChannelNames, BufferNodeNames, Tanks, TankNodeNames, TankChannelNames, 
)

from layout_gen.core.layout_db import LayoutDb
from layout_gen.subsystems.tanks.config import TankCfg

class TankImplementation(Protocol):
    def add_tank(
            self, 
            db: LayoutDb, 
            *, 
            nodes: TankNodeNames | BufferNodeNames,
            channels: TankChannelNames | BufferChannelNames,
            cfg: TankCfg
            ) -> None: ...


def add_tanks(
    db: LayoutDb,
    *,
    total_store_tanks: int,
    implementation: TankImplementation,
    cfg: TankCfg,
) -> None:
    db.misc["TotalStoreTanks"] = total_store_tanks

    tanks = Tanks(total_store_tanks)
    # buffer
    implementation.add_tank(
        db, 
        nodes=BufferNodeNames(),
        channels=BufferChannelNames(),
        cfg=cfg
    )    
    
    # storage tanks
    for idx in range(1, total_store_tanks + 1):
        implementation.add_tank(
            db,
            nodes=tanks.nodes[idx],
            channels=tanks.channels[idx],
            cfg=cfg
        )
        

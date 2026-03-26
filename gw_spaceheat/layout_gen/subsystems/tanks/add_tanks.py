from typing import Protocol

from gwsproto.names.hydronic_spaceheat.helpers import (
 BufferChannelNames, BufferNodeNames, TankNodeNames, TankChannelNames, 
)

from layout_gen.core.layout_db import LayoutDb
from layout_gen.subsystems.tanks.config import TankConfig, TanksConfig


class TankImplementation(Protocol):
    def add_tank(
            self, 
            db: LayoutDb, 
            *, 
            nodes: TankNodeNames | BufferNodeNames,
            channels: TankChannelNames | BufferChannelNames,
            cfg: TankConfig,
            ) -> None: ...


def add_tanks(
    db: LayoutDb,
    *,
    implementation: TankImplementation,
    cfgs: TanksConfig,

) -> None:

    hydronic = db.misc.setdefault("Hydronic", {})
    hydronic["TotalStoreTanks"] = len(cfgs.store)
    hydronic["StoreTankIndices"] = sorted(cfgs.store.keys())

    # buffer
    implementation.add_tank(
        db, 
        nodes=BufferNodeNames(),
        channels=BufferChannelNames(),
        cfg=cfgs.buffer
    )    
    
    # storage tanks
    for idx, cfg in sorted(cfgs.store.items()):
        if idx < 1 or idx > 6:
            raise ValueError(f"Tank idx {idx} out of valid range 1–6")

        implementation.add_tank(
            db,
            nodes=TankNodeNames(idx),
            channels=TankChannelNames(idx),
            cfg=cfg,
        )
        

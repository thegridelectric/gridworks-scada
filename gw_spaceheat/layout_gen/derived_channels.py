from pydantic import BaseModel
from layout_gen import LayoutDb
from gwsproto.named_types import DerivedChannelGt
from gwsproto.enums import GwUnit
# TODO: add to H0N and H0CN

class DerivedChConfig(BaseModel):
    Name: str
    CreatedByNodeName: str 
    Strategy: str
    OutputUnit: GwUnit
    
def add_derived_channel(db: LayoutDb, derived_cfg: DerivedChConfig) -> None:
    db.add_derived_channels(
        [DerivedChannelGt(
            Id = db.make_derived_channel_id(derived_cfg.Name),
            Name = derived_cfg.Name,
            CreatedByNodeName = derived_cfg.CreatedByNodeName,
            OutputUnit=derived_cfg.OutputUnit, 
            TerminalAssetAlias = db.terminal_asset_alias,
            Strategy = derived_cfg.Strategy,
            DisplayName = f"{derived_cfg.Name.title().replace('-','')} {derived_cfg.OutputUnit}",
            )
        ]
    )


    
        
    
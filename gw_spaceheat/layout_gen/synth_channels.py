from pydantic import BaseModel, PositiveInt
from layout_gen import LayoutDb
from typing import Any
from gwproto.named_types import SynthChannelGt
from gwproto.enums import TelemetryName
from gwsproto.data_classes.house_0_names import H0N, H0CN
# TODO: add to H0N and H0CN

class SynthConfig(BaseModel):
    Name: str = 'required-energy'
    CreatedByNodeName: str = 'synth-generator'
    Strategy: str = 'layer-by-layer'
    SyncReportMinutes: PositiveInt = 60
    TelemetryName: str = TelemetryName.WattHours.name

def add_synth(db: LayoutDb, synth_cfg: SynthConfig) -> None:

    db.add_synth_channels(
        [SynthChannelGt(
            Id = db.make_synth_channel_id(synth_cfg.Name),
            Name = synth_cfg.Name,
            CreatedByNodeName = synth_cfg.CreatedByNodeName,
            TelemetryName = synth_cfg.TelemetryName, 
            TerminalAssetAlias = db.terminal_asset_alias,
            Strategy = synth_cfg.Strategy,
            DisplayName = f"{synth_cfg.Name.title().replace('-','')} {synth_cfg.TelemetryName}",
            SyncReportMinutes = synth_cfg.SyncReportMinutes
            )
        ]
    )
"""Nolan hydronic knowledge. The Nolan choreography (iso/charge valve,
secondary pump, hp call) currently lives inline in the Nolan control
impls, which are slated for rewrite; it migrates here with that rewrite."""

from actors.hydronic.cold import ColdJudgmentNode
from actors.hydronic.shared import channels_fresh
from actors.scada_data import ScadaData
from gwsproto.data_classes.hydronic_layout import HydronicLayout
from gwsproto.names.hydronic_spaceheat.channel_names import HydronicSpaceheatChannelNames as HCN

# The channels Nolan control needs to judge the buffer: the band.
DISPATCH_CHANNELS = (HCN.buffer.depth1, HCN.buffer.depth3)


def buffer_fresh(data: ScadaData, layout: HydronicLayout) -> bool:
    """Nolan's band channels are enabled and fresh."""
    return channels_fresh(data, layout, DISPATCH_CHANNELS)


class NolanHydronic(ColdJudgmentNode):
    """The Nolan plant surface (choreography migrates here with the
    Nolan control rewrite)."""

    def buffer_fresh(self) -> bool:
        return buffer_fresh(self.data, self.layout)

    @property
    def buffer_temps_available(self):
        return self.data.buffer_temps_available

"""Nolan hydronic knowledge. The Nolan choreography (iso/charge valve,
secondary pump, hp call) currently lives inline in the Nolan control
impls, which are slated for rewrite; it migrates here with that rewrite."""

from actors.hydronic.cold import ColdJudgmentNode
from actors.hydronic.shared import buffer_fresh


class NolanHydronic(ColdJudgmentNode):
    """The Nolan plant surface (choreography migrates here with the
    Nolan control rewrite)."""

    def buffer_fresh(self) -> bool:
        return buffer_fresh(self.data, self.layout)

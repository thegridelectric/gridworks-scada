"""Nolan hydronic knowledge. The Nolan choreography (iso/charge valve,
secondary pump, hp call) currently lives inline in the Nolan control
impls, which are slated for rewrite; it migrates here with that rewrite."""

from actors.hydronic.shared import HydronicNode


class NolanHydronic(HydronicNode):
    """The Nolan plant surface (choreography migrates here with the
    Nolan control rewrite)."""

    @property
    def buffer_temps_available(self):
        return self.data.buffer_temps_available

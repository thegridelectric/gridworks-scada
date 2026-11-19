import math
import time
from typing import Iterable, Mapping

from plant_link import InProcessPlantLink
from scada_app import ScadaApp
from standing_plant import meter_values, standing_picos


class PlayedPlant:
    """The plant a test plays for a scada on a simulated layout. It is
    always there, and what it shows stands until the test changes it: each
    change reaches the scada as one whole flux, as a plant's does. It
    starts with every metered channel at 0 W, every tank at rest and every
    BTU-metered loop with standing flow and no lift."""

    def __init__(self, app: ScadaApp) -> None:
        link = app.plant_link
        assert isinstance(link, InProcessPlantLink)
        self.link = link
        link.silent_after_s = math.inf
        layout = app.hardware_layout
        self.values: dict[str, int] = meter_values(layout)
        self.metered_channel_names = list(self.values)
        self.hidden: set[str] = set()
        for pico in standing_picos(layout, time.time()):
            self.values.update(pico.values)
        self.scada_runs = False
        self.flux()

    def flux(self) -> None:
        # A channel handed to its actor as the flux arrives makes that actor
        # send, which it cannot do before its scada runs: until then the
        # plant shows only what is read when asked.
        self.link.show(
            {
                name: value
                for name, value in self.values.items()
                if name not in self.hidden
                and (self.scada_runs or name in self.link.polled_channels)
            },
            int(time.time() * 1000),
        )

    def scada_started(self) -> None:
        self.scada_runs = True
        self.flux()

    def show(self, values: Mapping[str, int]) -> None:
        self.values.update(values)
        self.flux()

    def hide(self, channel_names: Iterable[str]) -> None:
        """The plant shows every channel but these."""
        self.hidden = set(channel_names)
        self.flux()

    def meter_reads(self, watts: int) -> None:
        self.show({name: watts for name in self.metered_channel_names})

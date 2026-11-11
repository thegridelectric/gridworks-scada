import math
import time
from typing import Iterable, Mapping

from gwsproto.data_classes.components import ElectricMeterComponent
from gwsproto.enums import ActorClass

from plant_link import InProcessPlantLink
from scada_app import ScadaApp


class StandingPlant:
    """The plant a test plays for a scada on a simulated layout. It is
    always there, and what it shows stands until the test changes it: each
    change reaches the scada as one whole flux, as a plant's does. It
    starts with every metered channel at 0 W."""

    def __init__(self, app: ScadaApp) -> None:
        link = app.plant_link
        assert isinstance(link, InProcessPlantLink)
        self.link = link
        link.silent_after_s = math.inf
        self.metered_channel_names = [
            config.ChannelName
            for node in app.hardware_layout.nodes.values()
            if node.actor_class == ActorClass.PowerMeter
            and isinstance(node.component, ElectricMeterComponent)
            for config in node.component.gt.ConfigList
        ]
        self.hidden: set[str] = set()
        self.values: dict[str, int] = {name: 0 for name in self.metered_channel_names}
        self.flux()

    def flux(self) -> None:
        self.link.show(
            {name: value for name, value in self.values.items() if name not in self.hidden},
            int(time.time() * 1000),
        )

    def show(self, values: Mapping[str, int]) -> None:
        self.values.update(values)
        self.flux()

    def hide(self, channel_names: Iterable[str]) -> None:
        """The plant shows every channel but these."""
        self.hidden = set(channel_names)
        self.flux()

    def meter_reads(self, watts: int) -> None:
        self.show({name: watts for name in self.metered_channel_names})

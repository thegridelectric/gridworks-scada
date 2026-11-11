"""What stands behind each device node of a layout, chosen once where the
app is built: the plant link for a simulated device, the hardware itself
for any other."""

from typing import Optional

from gwsproto.data_classes.hydronic_layout import HydronicLayout

from pin_inputs import route_board_pins
from plant import Plant
from plant_link import PlantLink, route_simulated_devices
from relay_drives import route_board_relays


def route_devices(plant: Plant, layout: HydronicLayout, link: Optional[PlantLink]) -> None:
    if link is not None:
        route_simulated_devices(plant, layout, link)
    route_board_relays(plant, layout)
    route_board_pins(plant, layout)

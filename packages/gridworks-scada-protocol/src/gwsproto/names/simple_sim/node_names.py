from gwsproto.names.hydronic_spaceheat.helpers import (
    HydronicSpaceheatZoneNodeNames as HSZoneNodeNames,
)


class SimpleSimZoneNodeNames:
    """
    Node names in a simple-sim zone, mirroring the Nolan ones that matter for the
    shared detection mechanisms: self.opto (the whitewire reader). zone + whitewire
    structural nodes come from HydronicSpaceheatZoneNodeNames.
    """

    def __init__(self, zone_label: str, idx: int) -> None:
        hsznn = HSZoneNodeNames(zone_label, idx)
        if idx not in [1, 2, 3, 4, 5, 6]:
            raise Exception(f"Only supports 6 zones! No zone {idx}")
        zone = hsznn.zone

        # reading the whitewire from the SimSensor (same mechanism as the gw108 opto)
        self.opto = f"{zone}-opto"

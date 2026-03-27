from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneChannelNames as HSZoneChannelNames
from gwsproto.names.nolan.node_names import NolanNodeNames as NNN

class NolanChannelNames:
    floor_swt = NNN.floor_swt
    floor_rwt = NNN.floor_rwt

class NolanZoneChannelNames:
    """
    zone1-living-rm-floor-temp-raw, zone1-living-rm-floor-temp,
    zone1-living-rm-opto-input, zone1-living-rm-gw-temp
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        base = HSZoneChannelNames(zone_label, idx).base
        # floor raw temp name
        self.floor_temp_raw = f"{base}-floor-temp-raw" # DO NOT INCLUDE UNTIL API TANK MODULE REFACTOR
        self.floor_temp = f"{base}-floor-temp"

        # raw measurements
        self.opto_input = f"{base}-opto-input"
        self.gw_temp = f"{base}-gw-temp"



from gwsproto.names.hydronic_spaceheat.helpers import (
    HydronicSpaceheatZoneChannelNames as HSZoneChannelNames,
)


class SimpleSimChannelNames:
    """Top-level simple-sim channel names. The heat-pump relay-state channel
    (TelemetryName "RelayState"), AboutNodeName = the `hp-relay` node. Per the Nolan
    convention the relay-state channel name equals the relay node name.
    """

    hp_relay_state = "hp-relay"


class SimpleSimZoneChannelNames:
    """
    Raw zone channels for a simple-sim zone, mirroring the Nolan ones:
    zone1-main-opto-input, zone1-main-gw-temp

    The SimSensor emits these with the same names + detection mechanisms as the
    gw108/Nolan zone (opto-input → heat-call, gw-temp → setpoint). No floor temp,
    no stat-temp, no whitewire-pwr.
    """

    def __init__(self, zone_label: str, idx: int) -> None:
        base = HSZoneChannelNames(zone_label, idx).base

        # raw measurements (from the SimSensor)
        self.opto_input = f"{base}-opto-input"
        self.gw_temp = f"{base}-gw-temp"

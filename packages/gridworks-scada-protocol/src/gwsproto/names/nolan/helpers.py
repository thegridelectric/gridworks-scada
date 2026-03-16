from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneChannelNames as HSZoneChannelNames, HydronicSpaceheatZoneNodeNames as HSZoneNodeNames




class NolanZoneNodeNames:
    """
    Spaceheat Node names associated to a zone:
    self.zone_name, self.stat, self.whitewire
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        hsznn = HSZoneNodeNames(zone_label, idx)
        if idx not in [1,2,3,4,5,6]:
            raise Exception(f"Only supports 6 zones! No zone {idx}")
        self.zone = hsznn.zone
        self.stat = hsznn.stat
        self.whitewire = hsznn.whitewire

        self.floor = f"{self.zone}-floor"

        # reading whitewire w opto-coupler GPIO
        self.opto = f"{self.zone}-opto" 
        
        self.failsafe_relay = f"zone{idx}-failsafe"
        self.ops_relay = f"zone{idx}-scada"


class NolanZoneChannelNames:
    """
    Channel names associated to a Nolan zone.
    eg
     Inherited from HydronicSpaceheat
      - zone1-down-temp
      - zone1-down-set
      - zone1-down-heat-call
      - zone1-down-failsafe-relay
      - zone1-down-ops-relay

    """
    def __init__(self, zone_label: str, idx: int) -> None:
        hszcn = HSZoneChannelNames(zone_label, idx)
        base = hszcn.base

        # core semantic channels (likely derived)
        self.temp = hszcn.temp
        self.set = hszcn.set
        self.heat_call = hszcn.heat_call

        # floor raw temp name
        self.floor_temp_raw = f"{base}-floor-temp-raw"
        self.floor_temp = f"{base}-floor-temp"

        # relay states
        self.failsafe_relay_state = hszcn.failsafe_relay_state
        self.ops_relay_state = hszcn.ops_relay_state

        # raw measurements
        self.opto_input = f"{base}-opto-input"
        self.gw_temp = f"{base}-gw-temp"



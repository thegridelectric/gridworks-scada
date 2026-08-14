from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneNodeNames as HSZoneNodeNames


class NolanNodeNames:
    floor_swt = "floor-swt"
    floor_rwt = "floor-rwt"

    # relays
    vdc_relay = "vdc-relay-gpio-23"
    buffer_top_relay = "buffer-top-relay"
    buffer_bottom_relay = "buffer-bottom-relay"

    store_top_relay = "store-top-relay"
    store_bottom_relay = "store-bottom-relay"

    # The plant relays gw.nolan.layout axiom 3 (LocalControlPlant) forces
    # to exist — these constants mirror the sema contract, which is the
    # authority on the names.
    iso_valve_relay = "iso-valve-relay"
    secondary_pump_relay = "secondary-pump-relay"
    hp_scada_ops_relay = "hp-scada-ops-relay"


class NolanZoneNodeNames:
    """
    Node names in a Nolan Zone not in every Hydronic Spaceheat Zone
    self.floor, self.opto, self.failsafe_relay, 
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        hsznn = HSZoneNodeNames(zone_label, idx)
        if idx not in [1,2,3,4,5,6]:
            raise Exception(f"Only supports 6 zones! No zone {idx}")
        zone = hsznn.zone


        self.floor = f"{zone}-floor"

        # reading whitewire w opto-coupler GPIO
        self.opto = f"{zone}-opto" 
        
        self.failsafe_relay = f"zone{idx}-failsafe"
        self.ops_relay = f"zone{idx}-scada"

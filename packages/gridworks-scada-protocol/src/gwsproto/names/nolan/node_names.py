from gwsproto.names.hydronic_spaceheat.helpers import HydronicSpaceheatZoneNodeNames as HSZoneNodeNames


class NolanNodeNames:
    """Node names specific to a Nolan plant. A name states what the node
    DOES; where the wire lands on the gw108 is the component's RelayName
    (the board silkscreen), never the name.

    Names shared with hydronic_spaceheat (vdc-relay, the element nodes, the
    pumps, pipe temps) are NOT redeclared here — use
    HydronicSpaceheatNodeNames for those.
    """

    floor_swt = "floor-swt"
    floor_rwt = "floor-rwt"

    buffer_top_relay = "buffer-top-relay"
    buffer_bottom_relay = "buffer-bottom-relay"

    # The relays switching the store tank's two electric elements. The
    # elements themselves are HydronicSpaceheatNodeNames.store_top_elt /
    # store_bottom_elt.
    store_top_elt_relay = "store-top-elt-relay"
    store_bottom_elt_relay = "store-bottom-elt-relay"

    store_pump_relay = "store-pump-relay"

    # Nolan's discharge valve is an open/close valve (change.valve.state),
    # not House0's two-way charge/discharge valve.
    discharge_valve_relay = "discharge-valve-relay"

    # Plant relays gw.nolan.layout axiom 3 (LocalControlPlant) forces to
    # exist — these constants mirror the sema contract, which is the
    # authority on the names. The third, hp-scada-ops-relay, is shared with
    # House0 and so lives in HydronicSpaceheatNodeNames.
    iso_valve_relay = "iso-valve-relay"
    secondary_pump_relay = "secondary-pump-relay"


class NolanZoneNodeNames:
    """
    Node names in a Nolan Zone not in every Hydronic Spaceheat Zone
    self.floor, self.opto

    A zone's failsafe and ops relays are NOT here: both families name them
    identically (zone{i}-{label}-failsafe-relay / -ops-relay), so they come
    from the shared zone naming.
    """
    def __init__(self, zone_label: str, idx: int) -> None:
        hsznn = HSZoneNodeNames(zone_label, idx)
        if idx not in [1,2,3,4,5,6]:
            raise Exception(f"Only supports 6 zones! No zone {idx}")
        zone = hsznn.zone


        self.floor = f"{zone}-floor"

        # reading whitewire w opto-coupler GPIO
        self.opto = f"{zone}-opto"

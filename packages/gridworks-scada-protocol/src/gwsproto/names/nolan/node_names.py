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

    buffer_top_elt_relay = "buffer-top-elt-relay"
    buffer_bottom_elt_relay = "buffer-bottom-elt-relay"
    # The store tank's element relays are per tank: TankNodeNames(1).top_elt_relay.

    charge_valve_relay = "charge-valve-relay"

    # Plant relays gw.nolan.layout axiom 5 (RequiredActuators) forces to
    # exist — these constants mirror the sema contract, which is the
    # authority on the names. The third, hp-scada-ops-relay, is shared with
    # House0 and so lives in HydronicSpaceheatNodeNames.
    iso_valve_relay = "iso-valve-relay"
    secondary_pump_relay = "secondary-pump-relay"
    # The secondary pump's 0-10V speed input: a board DAC channel driven
    # as an actuator (ZeroTenOutputer with an i2c.dac.output component).
    secondary_010v = "secondary-010v"


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
